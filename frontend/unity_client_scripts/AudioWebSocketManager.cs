using System;
using System.Collections.Concurrent;
using System.Net.WebSockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
#if UNITY_WEBGL && !UNITY_EDITOR
using System.Runtime.InteropServices;
#endif

/// <summary>
/// Echo-Iris — Audio WebSocket Manager.
/// Handles microphone capture, PCM streaming to the server,
/// and receiving audio response chunks with RMS headers.
/// </summary>
public class AudioWebSocketManager
{
    // --- Wire format constants ---
    private const int HEADER_SIZE = 12;
    private const ushort MAGIC = 0x01CA; // 0xCA 0x01 as little-endian uint16
    private const int MIC_SAMPLE_RATE = 16000;
    private const int MIC_MAX_DURATION = 30; // seconds

    // --- WebSocket ---
    private ClientWebSocket _ws;
    private CancellationTokenSource _cts;
    private readonly byte[] _receiveBuffer = new byte[65536];

    // --- Main-thread queues ---
    private readonly ConcurrentQueue<Action> _mainThreadActions = new ConcurrentQueue<Action>();

    // --- Microphone state ---
    private AudioClip _micClip;
    private bool _isRecording;

    // --- Events ---
    public event Action<string> OnTranscriptReceived;
    public event Action<byte[], float> OnAudioChunkReceived; // (pcmData, rms)
    public event Action OnAudioStreamEnd;
    public event Action<string> OnEmotionReceived;
    public event Action<string> OnAnimationReceived;
    public event Action<string> OnAIReplyReceived;
    public event Action<string> OnError;

#if UNITY_WEBGL && !UNITY_EDITOR
    [DllImport("__Internal")]
    private static extern void AudioWebSocketInit(string url);

    [DllImport("__Internal")]
    private static extern void AudioWebSocketSendText(string message);

    [DllImport("__Internal")]
    private static extern void AudioWebSocketClose();

    [DllImport("__Internal")]
    private static extern void MicStartRecordingJS();

    [DllImport("__Internal")]
    private static extern void MicStopRecordingJS();
#endif

    /// <summary>Connect to the audio WebSocket endpoint.</summary>
    public async Task ConnectAsync(string url)
    {
        _cts = new CancellationTokenSource();

#if UNITY_WEBGL && !UNITY_EDITOR
        AudioWebSocketInit(url);
        await Task.CompletedTask;
#else
        _ws = new ClientWebSocket();
        await _ws.ConnectAsync(new Uri(url), _cts.Token);

        // Start background receive loop
        _ = Task.Run(() => ReceiveLoop(_cts.Token));
#endif
    }

    /// <summary>Start recording from the default microphone.</summary>
    public void StartRecording()
    {
        if (_isRecording) return;
        _isRecording = true;

#if !UNITY_WEBGL || UNITY_EDITOR
        string device = Microphone.devices.Length > 0 ? Microphone.devices[0] : null;
        _micClip = Microphone.Start(device, false, MIC_MAX_DURATION, MIC_SAMPLE_RATE);
#else
        MicStartRecordingJS();
#endif
    }

    /// <summary>
    /// Stop recording, convert to PCM, send to server, then signal end_audio.
    /// </summary>
    public async void StopRecordingAndSend()
    {
        if (!_isRecording) return;
        _isRecording = false;

#if !UNITY_WEBGL || UNITY_EDITOR
        // Get the actual recorded length
        string device = Microphone.devices.Length > 0 ? Microphone.devices[0] : null;
        int lastPos = Microphone.GetPosition(device);
        Microphone.End(device);

        if (lastPos == 0 || _micClip == null) return;

        // Convert AudioClip to PCM 16-bit LE bytes
        byte[] pcmBytes = ConvertClipToPCM16(_micClip, lastPos);

        if (_ws == null || _ws.State != WebSocketState.Open) return;

        try
        {
            // Send PCM as binary
            int chunkSize = 8192;
            for (int offset = 0; offset < pcmBytes.Length; offset += chunkSize)
            {
                int len = Mathf.Min(chunkSize, pcmBytes.Length - offset);
                var segment = new ArraySegment<byte>(pcmBytes, offset, len);
                bool isLast = (offset + len) >= pcmBytes.Length;
                await _ws.SendAsync(segment, WebSocketMessageType.Binary, isLast, _cts.Token);
            }

            // Send end_audio signal
            string endMsg = "{\"type\":\"end_audio\"}";
            byte[] endBytes = Encoding.UTF8.GetBytes(endMsg);
            await _ws.SendAsync(
                new ArraySegment<byte>(endBytes),
                WebSocketMessageType.Text,
                true,
                _cts.Token
            );
        }
        catch (Exception ex)
        {
            _mainThreadActions.Enqueue(() => OnError?.Invoke($"Send error: {ex.Message}"));
        }
#else
        // In WebGL, we trigger the JS function which stops the browser MediaRecorder
        // and sends the native end_audio websocket signal.
        try
        {
            MicStopRecordingJS();
        }
        catch (Exception ex)
        {
            _mainThreadActions.Enqueue(() => OnError?.Invoke($"Send error: {ex.Message}"));
        }
#endif
    }

    /// <summary>Send a text chat message to the server (skips STT, goes straight to Brain).</summary>
    public async void SendTextMessageAsync(string text)
    {
#if !UNITY_WEBGL || UNITY_EDITOR
        if (_ws == null || _ws.State != WebSocketState.Open) return;
#endif

        try
        {
            string json = $"{{\"type\":\"text_chat\",\"text\":\"{EscapeJson(text)}\"}}";

#if UNITY_WEBGL && !UNITY_EDITOR
            AudioWebSocketSendText(json);
#else
            byte[] bytes = Encoding.UTF8.GetBytes(json);
            await _ws.SendAsync(
                new ArraySegment<byte>(bytes),
                WebSocketMessageType.Text,
                true,
                _cts.Token
            );
#endif
        }
        catch (Exception ex)
        {
            _mainThreadActions.Enqueue(() => OnError?.Invoke($"Send text error: {ex.Message}"));
        }
    }

    /// <summary>Escape special characters for JSON string values.</summary>
    private static string EscapeJson(string s)
    {
        return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r");
    }

    /// <summary>Called from Update() to process queued actions on the main thread.</summary>
    public void ProcessMainThreadQueue()
    {
        while (_mainThreadActions.TryDequeue(out Action action))
        {
            action?.Invoke();
        }
    }

    /// <summary>Disconnect and clean up.</summary>
    public async Task DisconnectAsync()
    {
        _cts?.Cancel();

#if UNITY_WEBGL && !UNITY_EDITOR
        AudioWebSocketClose();
#else
        if (_ws != null && _ws.State == WebSocketState.Open)
        {
            try
            {
                await _ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", CancellationToken.None);
            }
            catch { }
        }
        _ws?.Dispose();
        _ws = null;
#endif
    }

    // --- Private ---

    private async Task ReceiveLoop(CancellationToken ct)
    {
        try
        {
            while (!ct.IsCancellationRequested && _ws.State == WebSocketState.Open)
            {
                using (var ms = new System.IO.MemoryStream())
                {
                    WebSocketReceiveResult result;
                    do
                    {
                        result = await _ws.ReceiveAsync(
                            new ArraySegment<byte>(_receiveBuffer), ct);

                        if (result.MessageType != WebSocketMessageType.Close)
                        {
                            ms.Write(_receiveBuffer, 0, result.Count);
                        }
                    }
                    while (!result.EndOfMessage && !ct.IsCancellationRequested);

                    if (result.MessageType == WebSocketMessageType.Close)
                        break;

                    byte[] messageBytes = ms.ToArray();

                    if (result.MessageType == WebSocketMessageType.Text)
                        {
                        string json = Encoding.UTF8.GetString(messageBytes);
                        HandleTextMessage(json);
                    }
                    else if (result.MessageType == WebSocketMessageType.Binary)
                    {
                        HandleBinaryMessage(messageBytes);
                    }
                }
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex)
        {
            _mainThreadActions.Enqueue(() => OnError?.Invoke($"Receive error: {ex.Message}"));
        }
    }

    public void HandleTextMessage(string json)
    {
        // Simple JSON parsing without external dependencies
        if (json.Contains("\"transcript\""))
        {
            // Extract text value: {"type":"transcript","text":"..."}
            string text = ExtractJsonValue(json, "text");
            _mainThreadActions.Enqueue(() => OnTranscriptReceived?.Invoke(text));
        }
        else if (json.Contains("\"emotion\"") && !json.Contains("\"error\""))
        {
            // Method B: {"type":"emotion","emotion":"Joy","animation":"Wave"}
            string emotion = ExtractJsonValue(json, "emotion");
            string animation = ExtractJsonValue(json, "animation");
            _mainThreadActions.Enqueue(() => OnEmotionReceived?.Invoke(emotion));
            if (!string.IsNullOrEmpty(animation))
                _mainThreadActions.Enqueue(() => OnAnimationReceived?.Invoke(animation));
        }
        else if (json.Contains("\"ai_reply\""))
        {
            // AI spoken text reply: {"type":"ai_reply","text":"..."}
            string reply = ExtractJsonValue(json, "text");
            _mainThreadActions.Enqueue(() => OnAIReplyReceived?.Invoke(reply));
        }
        else if (json.Contains("\"audio_end\""))
        {
            _mainThreadActions.Enqueue(() => OnAudioStreamEnd?.Invoke());
        }
        else if (json.Contains("\"error\""))
        {
            string error = ExtractJsonValue(json, "error");
            _mainThreadActions.Enqueue(() => OnError?.Invoke(error));
        }
    }

    public void HandleBinaryMessage(byte[] data)
    {
        if (data.Length < HEADER_SIZE) return;

        // Parse 12-byte header
        // Bytes 0-1: magic (0xCA 0x01)
        // Bytes 2-3: chunk_id (uint16 LE)
        // Bytes 4-7: data_len (uint32 LE)
        // Bytes 8-11: rms (float32 LE)
        ushort magic = BitConverter.ToUInt16(data, 0);
        if (magic != MAGIC) return;

        uint dataLen = BitConverter.ToUInt32(data, 4);
        float rms = BitConverter.ToSingle(data, 8);

        if (data.Length < HEADER_SIZE + (int)dataLen) return;

        // Copy PCM data
        byte[] pcmData = new byte[dataLen];
        Buffer.BlockCopy(data, HEADER_SIZE, pcmData, 0, (int)dataLen);

        _mainThreadActions.Enqueue(() => OnAudioChunkReceived?.Invoke(pcmData, rms));
    }

    /// <summary>Convert Unity AudioClip samples to PCM 16-bit signed LE bytes.</summary>
    private static byte[] ConvertClipToPCM16(AudioClip clip, int sampleCount)
    {
        float[] samples = new float[sampleCount * clip.channels];
        clip.GetData(samples, 0);

        byte[] pcm = new byte[samples.Length * 2]; // 2 bytes per sample
        for (int i = 0; i < samples.Length; i++)
        {
            // Clamp and convert float [-1,1] to int16
            float s = Mathf.Clamp(samples[i], -1f, 1f);
            short val = (short)(s * 32767f);
            pcm[i * 2] = (byte)(val & 0xFF);
            pcm[i * 2 + 1] = (byte)((val >> 8) & 0xFF);
        }
        return pcm;
    }

    /// <summary>Simple JSON string value extractor (no external deps).</summary>
    private static string ExtractJsonValue(string json, string key)
    {
        string search = $"\"{key}\":\"";
        int start = json.IndexOf(search);
        if (start < 0)
        {
            // Try with space after colon
            search = $"\"{key}\": \"";
            start = json.IndexOf(search);
            if (start < 0) return "";
        }
        start += search.Length;
        int end = json.IndexOf("\"", start);
        if (end < 0) return "";
        return json.Substring(start, end - start);
    }
}
