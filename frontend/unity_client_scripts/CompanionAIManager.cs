using System;
using UnityEngine;

/// <summary>
/// Echo-Iris — Top-level orchestrator.
/// Attach to a root GameObject. Manages audio, vision, and desktop mascot systems.
/// </summary>
public class EchoIrisManager : MonoBehaviour
{
    [Header("Server")]
    [Tooltip("Base WebSocket URL of the Echo-Iris backend")]
    public string serverUrl = "ws://localhost:8000";

    [Header("Components")]
    [Tooltip("Audio playback buffer (assign in inspector)")]
    public AudioPlaybackBuffer playbackBuffer;

    [Tooltip("Lip-sync controller (assign in inspector)")]
    public LipSyncController lipSync;

    [Tooltip("Animation controller for tricks/emotes (assign in inspector)")]
    public AvatarAnimationController animationController;

    [Header("Debug")]
    public bool logToConsole = true;

    // --- Internal managers ---
    private AudioWebSocketManager _audioManager;
    private VisionWebSocketManager _visionManager;

    // --- Events ---
    /// <summary>Fired when the AI transcript is received.</summary>
    public event Action<string> OnTranscript;

    /// <summary>Fired when the AI spoken text reply is received.</summary>
    public event Action<string> OnAIReply;

    /// <summary>Fired when audio playback finishes.</summary>
    public event Action OnAudioPlaybackComplete;

    /// <summary>Fired when a vision update arrives.</summary>
    public event Action<VisionUpdateData> OnVisionUpdate;

    /// <summary>Expose the internal AudioWebSocketManager for event subscriptions.</summary>
    public AudioWebSocketManager AudioManager => _audioManager;

    private void Awake()
    {
        // --- Audio ---
        _audioManager = new AudioWebSocketManager();
        _audioManager.OnTranscriptReceived += HandleTranscript;
        _audioManager.OnAudioChunkReceived += HandleAudioChunk;
        _audioManager.OnAudioStreamEnd += HandleAudioEnd;
        _audioManager.OnAIReplyReceived += HandleAIReply;
        _audioManager.OnError += HandleError;

        // --- Vision ---
        _visionManager = new VisionWebSocketManager();
        _visionManager.OnVisionUpdateReceived += HandleVisionUpdate;
        _visionManager.OnError += HandleError;

        // Connect
        ConnectAll();
    }

    private async void ConnectAll()
    {
        try
        {
            Log("Connecting to audio endpoint...");
            await _audioManager.ConnectAsync($"{serverUrl}/ws/audio");
            Log("Audio WebSocket connected.");

            Log("Connecting to vision endpoint...");
            await _visionManager.ConnectAsync($"{serverUrl}/ws/vision");
            Log("Vision WebSocket connected.");
        }
        catch (Exception ex)
        {
            Debug.LogError($"[Echo-Iris] Connection failed: {ex.Message}");
        }
    }

    private void Update()
    {
        // Pump message queues on main thread
        _audioManager?.ProcessMainThreadQueue();
        _visionManager?.ProcessMainThreadQueue();
    }

    // --- Public API ---

    /// <summary>Start recording from the microphone.</summary>
    public void StartRecording()
    {
        _audioManager?.StartRecording();
        Log("Recording started.");
    }

    /// <summary>Stop recording and send audio to the server.</summary>
    public void StopRecordingAndSend()
    {
        _audioManager?.StopRecordingAndSend();
        Log("Recording stopped, sending audio...");
    }

    /// <summary>Send a text message to the Brain (skips STT, goes straight to LLM → TTS).</summary>
    public void SendTextMessage(string text)
    {
        if (_audioManager != null)
        {
            _audioManager.SendTextMessageAsync(text);
            Log($"Sent text: {text}");
        }
    }

    /// <summary>Start streaming webcam frames to the vision endpoint.</summary>
    public void StartVisionCapture()
    {
        _visionManager?.StartCapture();
        Log("Vision capture started.");
    }

    /// <summary>Stop streaming webcam frames.</summary>
    public void StopVisionCapture()
    {
        _visionManager?.StopCapture();
        Log("Vision capture stopped.");
    }

    // --- Handlers ---

    private void HandleTranscript(string text)
    {
        Log($"Transcript: {text}");
        OnTranscript?.Invoke(text);
    }

    private void HandleAudioChunk(byte[] pcmData, float rms)
    {
        playbackBuffer?.EnqueuePCM(pcmData, rms);
    }

    private void HandleAudioEnd()
    {
        Log("Audio playback stream complete.");
        OnAudioPlaybackComplete?.Invoke();
    }

    private void HandleAIReply(string reply)
    {
        Log($"AI Reply: {reply}");
        OnAIReply?.Invoke(reply);
    }

    private void HandleVisionUpdate(VisionUpdateData data)
    {
        if (logToConsole && data.scene != null)
            Log($"Vision: {data.scene}");
        OnVisionUpdate?.Invoke(data);
    }

    /// <summary>
    /// Handle animation commands from the backend WebSocket.
    /// Expected JSON: {"type":"animation","action":"trick","trick":"flip"}
    /// Call this from your WebSocket message parser.
    /// </summary>
    public void HandleAnimationCommand(string action, string param)
    {
        if (animationController != null)
        {
            animationController.HandleAnimationCommand(action, param);
        }
    }

    private void HandleError(string error)
    {
        Debug.LogError($"[Echo-Iris] {error}");
    }

    private void Log(string msg)
    {
        if (logToConsole)
            Debug.Log($"[Echo-Iris] {msg}");
    }

#if UNITY_WEBGL
    // -----------------------------------------------------------------------
    // WebGL Javascript Interop Message Receivers
    // These methods are called by WebSocketJS.jslib using SendMessage()
    // -----------------------------------------------------------------------

    public void OnAudioWSOpenJS()
    {
        if (logToConsole) Debug.Log("[Echo-Iris] WebGL Audio WebSocket Opened (JS hook)");
    }

    public void OnAudioWSCloseJS()
    {
        if (logToConsole) Debug.Log("[Echo-Iris] WebGL Audio WebSocket Closed (JS hook)");
    }

    public void OnAudioWSErrorJS(string error)
    {
        HandleError($"WebGL Audio WS Error: {error}");
    }

    public void OnAudioWSTextJS(string text)
    {
        if (_audioManager != null)
        {
            _audioManager.HandleTextMessage(text);
        }
    }

    public void OnAudioWSBinaryJS(string base64)
    {
        if (_audioManager != null)
        {
            try
            {
                byte[] data = Convert.FromBase64String(base64);
                _audioManager.HandleBinaryMessage(data);
            }
            catch (Exception ex)
            {
                HandleError($"Failed to parse WebGL binary slice: {ex.Message}");
            }
        }
    }

    public void OnVisionWSErrorJS(string error)
    {
        HandleError($"WebGL Vision WS Error: {error}");
    }

    public void OnVisionWSTextJS(string text)
    {
        if (_visionManager != null)
        {
            _visionManager.HandleTextMessage(text);
        }
    }
#endif

    private async void OnDestroy()
    {
        if (_audioManager != null) await _audioManager.DisconnectAsync();
        if (_visionManager != null) await _visionManager.DisconnectAsync();
    }
}
