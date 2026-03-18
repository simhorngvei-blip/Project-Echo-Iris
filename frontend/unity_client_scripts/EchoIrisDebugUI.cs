using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;

/// <summary>
/// Echo-Iris Debug Dashboard
/// Provides an OnGUI-based interface to monitor and test all subsystems:
/// Chat (with live TTS), Audio, Vision, Expressions, Mascot Control, and Tools.
///
/// Attach to any GameObject in the scene and assign the references.
/// </summary>
public class EchoIrisDebugUI : MonoBehaviour
{
    [Header("Subsystem References")]
    [Tooltip("The main orchestrator (handles recording, vision capture, and text chat)")]
    public EchoIrisManager echoIrisManager;

    [Tooltip("The audio buffer (handles RMS and playback)")]
    public AudioPlaybackBuffer audioBuffer;

    [Tooltip("The desktop roam state machine")]
    public DesktopRoamController roamController;

    [Tooltip("The unified avatar controller for expressions, lip-sync, and animations")]
    public EchoIrisAvatarController avatarController;

    // --- GUI State ---
    private string _chatInput = "Hello! How are you?";
    private string _latestYolo = "None";
    private string _latestScene = "None";
    private string _serverBaseUrl = "http://localhost:8000";
    
    private Vector2 _scrollPosition;
    private readonly List<string> _transcripts = new List<string>();
    private const int MaxTranscripts = 10;

    // GUI Layout constants
    private const float BoxPadding = 10f;

    // Emotion list for the expression tester
    private static readonly string[] Emotions = { 
        "Neutral", "Joy", "Angry", "Sorrow", "Fun", "Surprised",
        "Smug", "Despair", "Shy", "Confused", "Excited", "Love" 
    };

    private void OnEnable()
    {
        if (echoIrisManager != null)
        {
            echoIrisManager.OnTranscript += HandleTranscript;
            echoIrisManager.OnAIReply += HandleAIReply;
            echoIrisManager.OnVisionUpdate += HandleVisionUpdate;
        }
    }

    private void OnDisable()
    {
        if (echoIrisManager != null)
        {
            echoIrisManager.OnTranscript -= HandleTranscript;
            echoIrisManager.OnAIReply -= HandleAIReply;
            echoIrisManager.OnVisionUpdate -= HandleVisionUpdate;
        }
    }

    private void HandleTranscript(string text)
    {
        _transcripts.Add($"<color=#88ccff>[You]</color> {text}");
        TrimTranscripts();
        _scrollPosition.y = Mathf.Infinity;
    }

    private void HandleAIReply(string reply)
    {
        _transcripts.Add($"<color=#ffcc44>[Emily]</color> {reply}");
        TrimTranscripts();
        _scrollPosition.y = Mathf.Infinity;
    }

    private void TrimTranscripts()
    {
        while (_transcripts.Count > MaxTranscripts)
            _transcripts.RemoveAt(0);
    }

    private void HandleVisionUpdate(VisionUpdateData update)
    {
        if (update != null)
        {
            if (!string.IsNullOrEmpty(update.scene))
            {
                _latestScene = update.scene;
            }
            
            if (update.objects != null && update.objects.Length > 0)
            {
                List<string> labels = new List<string>();
                foreach (var obj in update.objects)
                {
                    labels.Add($"{obj.label} ({Mathf.RoundToInt(obj.confidence * 100)}%)");
                }
                _latestYolo = string.Join(", ", labels);
            }
            else
            {
                _latestYolo = "None";
            }
        }
    }

    // =========================================================================
    // ONGUI RENDER LOOP
    // =========================================================================

#if !UNITY_WEBGL || UNITY_EDITOR
    private void OnGUI()
    {
        // Define a master container on the left side of the screen
        GUILayout.BeginArea(new Rect(10, 10, 350, Screen.height - 20));

        // ---------------------------------------------------------
        // 1. Core Intelligence & Chat (LIVE text chat)
        // ---------------------------------------------------------
        GUILayout.BeginVertical("box");
        GUILayout.Label("<b>1. Core Intelligence & Chat</b>", GetStyleHeader());
        
        GUILayout.BeginHorizontal();
        _chatInput = GUILayout.TextField(_chatInput, GUILayout.ExpandWidth(true));
        
        if (GUILayout.Button("Send to Brain", GUILayout.Width(100)))
        {
            if (echoIrisManager != null && !string.IsNullOrEmpty(_chatInput))
            {
                echoIrisManager.SendTextMessage(_chatInput);
                _chatInput = "";
            }
        }
        GUILayout.EndHorizontal();

        // Check for Enter key submit
        if (Event.current.type == EventType.KeyDown && Event.current.keyCode == KeyCode.Return)
        {
            if (echoIrisManager != null && !string.IsNullOrEmpty(_chatInput))
            {
                echoIrisManager.SendTextMessage(_chatInput);
                _chatInput = "";
                Event.current.Use();
            }
        }

        // Transcript Terminal Area (shows both user and AI messages)
        GUILayout.Space(5);
        GUILayout.Label("<i>Chat History:</i>", GetStyleItalic());
        
        _scrollPosition = GUILayout.BeginScrollView(_scrollPosition, "box", GUILayout.Height(120));
        foreach (var t in _transcripts)
        {
            GUILayout.Label(t, GetStyleTerminal());
        }
        GUILayout.EndScrollView();
        
        GUILayout.EndVertical();
        GUILayout.Space(BoxPadding);


        // ---------------------------------------------------------
        // 2. Audio Subsystem
        // ---------------------------------------------------------
        GUILayout.BeginVertical("box");
        GUILayout.Label("<b>2. Audio Subsystem (STT/TTS)</b>", GetStyleHeader());
        
        GUILayout.BeginHorizontal();
        if (GUILayout.Button("🎤 Start Recording"))
        {
            if (echoIrisManager != null) echoIrisManager.StartRecording();
        }
        if (GUILayout.Button("⏸ Stop & Send Audio"))
        {
            if (echoIrisManager != null) echoIrisManager.StopRecordingAndSend();
        }
        GUILayout.EndHorizontal();

        string currentRms = audioBuffer != null ? audioBuffer.CurrentRMS.ToString("F4") : "N/A";
        GUILayout.Label($"<b>AudioPlaybackBuffer RMS:</b> {currentRms} {(audioBuffer != null && audioBuffer.IsPlaying ? "<color=green>[PLAYING]</color>" : "")}");
        
        GUILayout.EndVertical();
        GUILayout.Space(BoxPadding);


        // ---------------------------------------------------------
        // 3. Vision Subsystem
        // ---------------------------------------------------------
        GUILayout.BeginVertical("box");
        GUILayout.Label("<b>3. Vision Subsystem</b>", GetStyleHeader());
        
        GUILayout.BeginHorizontal();
        if (GUILayout.Button("👁 Start Vision Stream"))
        {
            if (echoIrisManager != null) echoIrisManager.StartVisionCapture();
        }
        if (GUILayout.Button("🚫 Stop Vision Stream"))
        {
            if (echoIrisManager != null) echoIrisManager.StopVisionCapture();
        }
        GUILayout.EndHorizontal();

        GUILayout.Label("<b>Latest YOLO:</b> " + _latestYolo);
        GUILayout.Label("<b>Latest LLaVA Scene:</b> " + _latestScene);

        GUILayout.EndVertical();
        GUILayout.Space(BoxPadding);


        // ---------------------------------------------------------
        // 4. Expression Tester
        // ---------------------------------------------------------
        GUILayout.BeginVertical("box");
        GUILayout.Label("<b>4. Expression Tester</b>", GetStyleHeader());

        // Current emotion display
        string currentEmotion = avatarController != null ? "Active" : "N/A (assign EchoIrisAvatarController)";
        GUILayout.Label($"<i>Click an emotion to preview it on the avatar:</i>", GetStyleItalic());

        // We have 12 emotions. Split them into 3 rows of 4 for a clean grid.
        for (int row = 0; row < 3; row++)
        {
            GUILayout.BeginHorizontal();
            for (int col = 0; col < 4; col++)
            {
                int index = (row * 4) + col;
                if (index < Emotions.Length)
                {
                    string emotion = Emotions[index];
                    if (GUILayout.Button(emotion))
                    {
                        if (avatarController != null)
                        {
                            avatarController.HandleEmotionReceived(emotion);
                            Debug.Log($"[DebugUI] Expression test: {emotion}");
                        }
                    }
                }
            }
            GUILayout.EndHorizontal();
        }

        GUILayout.EndVertical();
        GUILayout.Space(BoxPadding);


        // ---------------------------------------------------------
        // 5. Mascot Control
        // ---------------------------------------------------------
        GUILayout.BeginVertical("box");
        GUILayout.Label("<b>5. Mascot Control (Roaming & Tricks)</b>", GetStyleHeader());

        string state = roamController != null ? roamController.CurrentState.ToString() : "N/A";
        GUILayout.Label($"<b>Roam State:</b> {state}");

        GUILayout.BeginHorizontal();
        if (GUILayout.Button("Force Idle"))
        {
            if (roamController != null) roamController.ForceIdle();
        }
        if (GUILayout.Button("Walk to Center"))
        {
            if (roamController != null) roamController.WalkToScreenPosition(Screen.width / 2f);
        }
        if (GUILayout.Button("Do Random Trick"))
        {
            if (avatarController != null) avatarController.PlayRandomTrick();
        }
        GUILayout.EndHorizontal();

        GUILayout.EndVertical();
        GUILayout.Space(BoxPadding);


        // ---------------------------------------------------------
        // 6. Action Tools
        // ---------------------------------------------------------
        GUILayout.BeginVertical("box");
        GUILayout.Label("<b>6. Action Tools & Robot Integration</b>", GetStyleHeader());
        
        GUILayout.BeginHorizontal();
        if (GUILayout.Button("Test set_timer()"))
        {
            StartCoroutine(PostTool("/api/tools/timer",
                "{\"seconds\":60,\"message\":\"Time to stretch!\"}"));
        }
        if (GUILayout.Button("Test open_app()"))
        {
            StartCoroutine(PostTool("/api/tools/open_app",
                "{\"app_name\":\"notepad\"}"));
        }
        if (GUILayout.Button("Test robot cmd"))
        {
            StartCoroutine(PostTool("/api/tools/robot",
                "{\"action\":\"wave_arm\",\"parameters\":\"{}\"}")); 
        }
        GUILayout.EndHorizontal();

        GUILayout.EndVertical();


        GUILayout.EndArea();
    }
#endif

    // =========================================================================
    // HELPER STYLES
    // =========================================================================

    private GUIStyle GetStyleHeader()
    {
        GUIStyle style = new GUIStyle(GUI.skin.label)
        {
            richText = true,
            fontSize = 14,
            alignment = TextAnchor.MiddleLeft
        };
        return style;
    }

    private GUIStyle GetStyleItalic()
    {
        GUIStyle style = new GUIStyle(GUI.skin.label)
        {
            richText = true,
            fontSize = 12
        };
        return style;
    }

    private GUIStyle GetStyleTerminal()
    {
        GUIStyle style = new GUIStyle(GUI.skin.label)
        {
            richText = true,
            fontSize = 12,
            wordWrap = true
        };
        // Light green terminal text
        style.normal.textColor = new Color(0.2f, 0.9f, 0.2f);
        return style;
    }

    /// <summary>POST JSON to a REST tool endpoint.</summary>
    private IEnumerator PostTool(string path, string jsonBody)
    {
        string url = _serverBaseUrl + path;
        Debug.Log($"[DebugUI] POST {url}");

        byte[] bodyRaw = Encoding.UTF8.GetBytes(jsonBody);
        using var request = new UnityWebRequest(url, "POST");
        request.uploadHandler = new UploadHandlerRaw(bodyRaw);
        request.downloadHandler = new DownloadHandlerBuffer();
        request.SetRequestHeader("Content-Type", "application/json");

        yield return request.SendWebRequest();

        if (request.result == UnityWebRequest.Result.Success)
        {
            Debug.Log($"[DebugUI] Tool OK: {request.downloadHandler.text}");
            _transcripts.Add($"<color=#88ff88>[Tool]</color> {request.downloadHandler.text}");
            TrimTranscripts();
        }
        else
        {
            Debug.LogError($"[DebugUI] Tool FAIL: {request.error}");
            _transcripts.Add($"<color=#ff4444>[Tool Error]</color> {request.error}");
            TrimTranscripts();
        }
    }
}
