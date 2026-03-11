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
/// Data class for vision update messages from the server.
/// </summary>
[Serializable]
public class VisionUpdateData
{
    public VisionObject[] objects;
    public string scene;
    public bool injected;
}

/// <summary>
/// A single detected object from YOLO.
/// </summary>
[Serializable]
public class VisionObject
{
    public string label;
    public float confidence;
}

/// <summary>
/// Echo-Iris — Vision WebSocket Manager.
/// Captures webcam frames via WebCamTexture, compresses to JPEG,
/// encodes as base64, and streams to /ws/vision at a set interval.
/// </summary>
public class VisionWebSocketManager
{
    // --- Settings ---
    private const float DEFAULT_CAPTURE_INTERVAL = 0.1f; // 10 FPS
    private const int DEFAULT_JPEG_QUALITY = 50;

    // --- WebSocket ---
    private ClientWebSocket _ws;
    private CancellationTokenSource _cts;
    private readonly byte[] _receiveBuffer = new byte[65536];

    // --- Camera ---
    private WebCamTexture _camTexture;
    private Texture2D _captureTexture;
    private bool _isCapturing;
    private float _lastCaptureTime;
    private float _captureInterval = DEFAULT_CAPTURE_INTERVAL;
    private int _jpegQuality = DEFAULT_JPEG_QUALITY;

    // --- Main-thread queues ---
    private readonly ConcurrentQueue<Action> _mainThreadActions = new ConcurrentQueue<Action>();

    // --- Events ---
    public event Action<VisionUpdateData> OnVisionUpdateReceived;
    public event Action<string> OnError;

#if UNITY_WEBGL && !UNITY_EDITOR
    [DllImport("__Internal")]
    private static extern void VisionWebSocketInit(string url);

    [DllImport("__Internal")]
    private static extern void VisionWebSocketSendText(string message);

    [DllImport("__Internal")]
    private static extern void VisionWebSocketClose();
#endif

    /// <summary>Connect to the vision WebSocket endpoint.</summary>
    public async Task ConnectAsync(string url)
    {
        _cts = new CancellationTokenSource();

#if UNITY_WEBGL && !UNITY_EDITOR
        VisionWebSocketInit(url);
        // In WebGL, receiving is handled by the browser calling Unity Message methods,
        // which must be attached to a specific GameObject (handled in EchoIrisManager)
        await Task.CompletedTask;
#else
        _ws = new ClientWebSocket();
        await _ws.ConnectAsync(new Uri(url), _cts.Token);

        // Start background receive loop
        _ = Task.Run(() => ReceiveLoop(_cts.Token));
#endif
    }

    /// <summary>Start capturing and streaming webcam frames.</summary>
    public void StartCapture()
    {
        if (_isCapturing) return;

#if !UNITY_WEBGL || UNITY_EDITOR
        // Find and start webcam
        if (WebCamTexture.devices.Length == 0)
        {
            _mainThreadActions.Enqueue(() => OnError?.Invoke("No webcam found"));
            return;
        }

        _camTexture = new WebCamTexture(WebCamTexture.devices[0].name, 640, 480, 15);
        _camTexture.Play();
        _isCapturing = true;
        _lastCaptureTime = Time.time;
#else
        _mainThreadActions.Enqueue(() => OnError?.Invoke("WebCamTexture is not supported natively in WebGL without a custom jslib. Vision disabled."));
#endif
    }

    /// <summary>Stop capturing webcam frames.</summary>
    public void StopCapture()
    {
        _isCapturing = false;
        if (_camTexture != null && _camTexture.isPlaying)
        {
            _camTexture.Stop();
        }
    }

    /// <summary>Called from Update() to process queued actions and capture frames.</summary>
    public void ProcessMainThreadQueue()
    {
        // Process incoming messages
        while (_mainThreadActions.TryDequeue(out Action action))
        {
            action?.Invoke();
        }

        // Capture and send frames at interval
        if (_isCapturing && _camTexture != null && _camTexture.isPlaying)
        {
            if (Time.time - _lastCaptureTime >= _captureInterval)
            {
                _lastCaptureTime = Time.time;
                CaptureAndSendFrame();
            }
        }
    }

    /// <summary>Disconnect and clean up.</summary>
    public async Task DisconnectAsync()
    {
        StopCapture();
        _cts?.Cancel();

#if UNITY_WEBGL && !UNITY_EDITOR
        VisionWebSocketClose();
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

        if (_captureTexture != null)
        {
            UnityEngine.Object.Destroy(_captureTexture);
            _captureTexture = null;
        }
    }

    // --- Private ---

    private async void CaptureAndSendFrame()
    {
#if !UNITY_WEBGL || UNITY_EDITOR
        if (_ws == null || _ws.State != WebSocketState.Open) return;
#endif
        if (_camTexture == null || !_camTexture.didUpdateThisFrame) return;

        try
        {
            // Create or resize capture texture
            if (_captureTexture == null ||
                _captureTexture.width != _camTexture.width ||
                _captureTexture.height != _camTexture.height)
            {
                if (_captureTexture != null)
                    UnityEngine.Object.Destroy(_captureTexture);
                _captureTexture = new Texture2D(
                    _camTexture.width, _camTexture.height,
                    TextureFormat.RGB24, false);
            }

            // Copy webcam pixels (Main Thread)
            _captureTexture.SetPixels(_camTexture.GetPixels());
            _captureTexture.Apply();

            // Extract raw bytes to pass to background thread
            byte[] rawPixels = _captureTexture.GetRawTextureData();
            int width = _captureTexture.width;
            int height = _captureTexture.height;
            int quality = _jpegQuality;

            // Offload encoding to a background thread to prevent stutter
            string jsonString = await Task.Run(() =>
            {
                // Encode to JPEG
                byte[] jpegBytes = ImageConversion.EncodeArrayToJPG(
                    rawPixels, GraphicsFormat.R8G8B8_UNorm, (uint)width, (uint)height, (uint)(width * 3), quality);

                // Convert to base64
                string b64 = Convert.ToBase64String(jpegBytes);

                // Build JSON message
                return $"{{\"type\":\"frame\",\"data\":\"{b64}\"}}";
            });

            // Send
#if UNITY_WEBGL && !UNITY_EDITOR
            VisionWebSocketSendText(jsonString);
#else
            byte[] msgBytes = Encoding.UTF8.GetBytes(jsonString);
            await _ws.SendAsync(
                new ArraySegment<byte>(msgBytes),
                WebSocketMessageType.Text,
                true,
                _cts.Token
            );
#endif
        }
        catch (Exception ex)
        {
            _mainThreadActions.Enqueue(() => OnError?.Invoke($"Vision send error: {ex.Message}"));
        }
    }

#if !UNITY_WEBGL || UNITY_EDITOR
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

                    if (result.MessageType == WebSocketMessageType.Text)
                    {
                        byte[] messageBytes = ms.ToArray();
                        string json = Encoding.UTF8.GetString(messageBytes);
                        HandleTextMessage(json);
                    }
                }
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex)
        {
            _mainThreadActions.Enqueue(() => OnError?.Invoke($"Vision receive error: {ex.Message}"));
        }
    }
#endif

    public void HandleTextMessage(string json)
    {
        if (json.Contains("\"vision_update\""))
        {
            try
            {
                var data = JsonUtility.FromJson<VisionUpdateData>(json);
                _mainThreadActions.Enqueue(() => OnVisionUpdateReceived?.Invoke(data));
            }
            catch (Exception ex)
            {
                _mainThreadActions.Enqueue(() =>
                    OnError?.Invoke($"Vision parse error: {ex.Message}"));
            }
        }
        else if (json.Contains("\"error\""))
        {
            string error = ExtractJsonValue(json, "error");
            _mainThreadActions.Enqueue(() => OnError?.Invoke($"Vision server: {error}"));
        }
    }

    /// <summary>Simple JSON string value extractor.</summary>
    private static string ExtractJsonValue(string json, string key)
    {
        string search = $"\"{key}\":\"";
        int start = json.IndexOf(search);
        if (start < 0)
        {
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
