using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Echo-Iris — Avatar Action Controller.
/// Unified controller that receives emotion + animation data from the
/// WebSocket and drives both facial blendshapes and body animations.
///
/// REPLACES ExpressionController.cs — disable that script if using this one.
///
/// Setup:
///   1. Attach to the same GameObject as your VRM avatar (needs Animator).
///   2. Assign the SkinnedMeshRenderer (face mesh) in the Inspector.
///   3. Assign the AudioWebSocketManager reference.
///   4. Optionally assign AudioPlaybackBuffer for auto-fade after audio ends.
///
/// Supported emotions: Neutral, Joy, Angry, Sorrow, Fun, Surprised
/// Supported animations: Idle, Wave, Nod (+ any Animator triggers you add)
/// </summary>
[RequireComponent(typeof(Animator))]
public class AvatarActionController : MonoBehaviour
{
    // -----------------------------------------------------------------------
    // Inspector Fields
    // -----------------------------------------------------------------------

    [Header("References")]
    [Tooltip("The avatar's face SkinnedMeshRenderer containing expression blendshapes.")]
    public SkinnedMeshRenderer faceMesh;

    [Tooltip("Reference to the EchoIrisManager (we get the AudioWebSocketManager from this).")]
    public EchoIrisManager echoIrisManager;

    [Tooltip("Reference to AudioPlaybackBuffer (for auto-fade to Neutral after audio ends).")]
    public AudioPlaybackBuffer playbackBuffer;

    [Header("Expression Tuning")]
    [Tooltip("How fast expressions transition. Higher = faster blending.")]
    [Range(1f, 20f)]
    public float transitionSpeed = 8f;

    [Tooltip("Maximum blendshape weight for emotions (0–100).")]
    [Range(0f, 100f)]
    public float maxWeight = 80f;

    [Tooltip("Seconds to hold the expression after audio ends before fading to Neutral.")]
    public float holdDuration = 1.0f;

    [Header("Blendshape Index Overrides (set to -1 for auto-detect)")]
    public int joyIndex = -1;
    public int angryIndex = -1;
    public int sorrowIndex = -1;
    public int funIndex = -1;
    public int surprisedIndex = -1;
    public int smugIndex = -1;
    public int despairIndex = -1;
    public int shyIndex = -1;
    public int confusedIndex = -1;
    public int excitedIndex = -1;
    public int loveIndex = -1;

    // -----------------------------------------------------------------------
    // Private State
    // -----------------------------------------------------------------------

    private Animator _animator;

    // Emotion → list of blendshape indices (populated at Start)
    private Dictionary<string, List<int>> _emotionToIndices = new Dictionary<string, List<int>>();

    // Current and target emotion
    private string _targetEmotion = "Neutral";
    private float _holdTimer;
    private bool _manualOverride; // When true, auto-fade to Neutral is disabled

    // Smoothed blendshape weights (one per emotion)
    private Dictionary<string, float> _currentWeights = new Dictionary<string, float>();

    // Dictionary mapping an emotion string to a list of blendshape keywords.
    // ANY blendshape name containing ANY of these keywords will be added to the multiple-blendshape list for that emotion.
    private static readonly Dictionary<string, string[]> EmotionBlendshapes = new Dictionary<string, string[]>()
    {
        // Custom user combinations
        { "Joy", new[] { "笑い", "はう", "はわ", "joy", "smile", "happy" } },
        { "Angry", new[] { "怒り", "おこ", "チーク", "angry", "anger" } },
        { "Sorrow", new[] { "悲しい", "涙", "むう", "ハイライト拡大", "sorrow", "sad" } },
        
        // Single mappings
        { "Fun", new[] { "にこり", "fun", "excited", "cheerful" } },
        { "Surprised", new[] { "びっくり", "surprise", "surprised" } },
        { "Smug", new[] { "にやり", "smug", "smirk" } },
        { "Despair", new[] { "絶望", "despair", "shock" } },
        { "Shy", new[] { "チーク", "shy", "blush" } },
        { "Confused", new[] { "グルグル", "confused", "dizzy" } },
        { "Excited", new[] { "星瞳", "star" } },
        { "Love", new[] { "ハート瞳", "love", "heart" } }
    };

    // All supported emotion strings
    private static readonly string[] AllEmotions = { 
        "Joy", "Angry", "Sorrow", "Fun", "Surprised",
        "Smug", "Despair", "Shy", "Confused", "Excited", "Love" 
    };

    // -----------------------------------------------------------------------
    // Unity Lifecycle
    // -----------------------------------------------------------------------

    private void Awake()
    {
        _animator = GetComponent<Animator>();
    }

    private void Start()
    {
        // Initialise weight tracking for each emotion
        foreach (string emotion in AllEmotions)
        {
            _currentWeights[emotion] = 0f;
        }

        // Auto-detect blendshape indices (or use Inspector overrides)
        if (faceMesh != null)
        {
            BuildEmotionDictionary();
        }
        else
        {
            Debug.LogWarning("[AvatarAction] No SkinnedMeshRenderer assigned!");
        }

        // Subscribe to audio events here (guaranteed that EchoIrisManager.Awake() is finished)
        if (echoIrisManager != null && echoIrisManager.AudioManager != null)
        {
            echoIrisManager.AudioManager.OnEmotionReceived += HandleEmotionReceived;
            echoIrisManager.AudioManager.OnAnimationReceived += HandleAnimationReceived;
            echoIrisManager.AudioManager.OnAudioStreamEnd += HandleAudioEnd;
        }
    }

    private void OnDestroy()
    {
        if (echoIrisManager != null && echoIrisManager.AudioManager != null)
        {
            echoIrisManager.AudioManager.OnEmotionReceived -= HandleEmotionReceived;
            echoIrisManager.AudioManager.OnAnimationReceived -= HandleAnimationReceived;
            echoIrisManager.AudioManager.OnAudioStreamEnd -= HandleAudioEnd;
        }
    }

    /// <summary>
    /// Every frame: smoothly lerp each emotion blendshape toward its target
    /// weight, and auto-fade to Neutral after audio playback ends.
    /// </summary>
    private void Update()
    {
        // --- Auto-fade logic: hold expression briefly after audio ends ---
        // Only auto-fade if NOT in manual override mode (manual = Debug UI button press)
        if (!_manualOverride && playbackBuffer != null && !playbackBuffer.IsPlaying)
        {
            if (_holdTimer > 0f)
            {
                _holdTimer -= Time.deltaTime;
            }
            else if (_targetEmotion != "Neutral")
            {
                _targetEmotion = "Neutral";
            }
        }

        // --- Smooth blendshape interpolation ---
        if (faceMesh == null) return;

        float dt = Time.deltaTime * transitionSpeed;

        // 1. Calculate the smoothed weight for every emotion
        foreach (string emotion in AllEmotions)
        {
            float target = (_targetEmotion == emotion) ? maxWeight : 0f;
            float current = _currentWeights[emotion];
            _currentWeights[emotion] = Mathf.Lerp(current, target, dt);
        }

        // 2. Aggregate the maximum weight for each individual blendshape index.
        // This prevents overlapping blendshapes (like "チーク" in both Angry and Shy) 
        // from instantly overwriting each other to 0.
        Dictionary<int, float> finalIndexWeights = new Dictionary<int, float>();

        foreach (string emotion in AllEmotions)
        {
            float weight = _currentWeights[emotion];
            
            if (_emotionToIndices.TryGetValue(emotion, out List<int> indices))
            {
                foreach (int index in indices)
                {
                    if (index >= 0)
                    {
                        if (finalIndexWeights.TryGetValue(index, out float existingWeight))
                        {
                            finalIndexWeights[index] = Mathf.Max(existingWeight, weight);
                        }
                        else
                        {
                            finalIndexWeights[index] = weight;
                        }
                    }
                }
            }
        }

        // 3. Apply the aggregated weights to the mesh exactly once per frame
        foreach (var kvp in finalIndexWeights)
        {
            faceMesh.SetBlendShapeWeight(kvp.Key, kvp.Value);
        }
    }

    // -----------------------------------------------------------------------
    // Public API (called from WebSocket events)
    // -----------------------------------------------------------------------

    /// <summary>Set the target emotion. Called from WebSocket events or Debug UI.</summary>
    public void HandleEmotionReceived(string emotion)
    {
        _targetEmotion = string.IsNullOrEmpty(emotion) ? "Neutral" : emotion;
        _holdTimer = 0f;
        // If audio is currently playing, this is a WebSocket-driven emotion
        // and should auto-fade when audio ends. Otherwise it's manual (Debug UI).
        _manualOverride = (playbackBuffer == null || !playbackBuffer.IsPlaying);
        Debug.Log($"[AvatarAction] Emotion → {_targetEmotion} (manual={_manualOverride})");
    }

    /// <summary>
    /// Fire an Animator trigger for the given animation string.
    /// "Idle" is a no-op (no trigger fired).
    /// </summary>
    public void HandleAnimationReceived(string animation)
    {
        if (string.IsNullOrEmpty(animation) || animation == "Idle")
            return; // Idle = do nothing, let current state play

        // Fire the trigger on the Animator (e.g., "Wave", "Nod")
        _animator.SetTrigger(animation);
        Debug.Log($"[AvatarAction] Animation trigger → {animation}");
    }

    /// <summary>Start the hold timer when audio stream ends, clear manual override.</summary>
    private void HandleAudioEnd()
    {
        _manualOverride = false;
        _holdTimer = holdDuration;
    }

    /// <summary>Force all expressions to Neutral immediately.</summary>
    public void ResetExpression()
    {
        _targetEmotion = "Neutral";

        foreach (string emotion in AllEmotions)
        {
            _currentWeights[emotion] = 0f;

            if (_emotionToIndices.TryGetValue(emotion, out List<int> indices))
            {
                foreach (int index in indices)
                {
                    if (index >= 0)
                        faceMesh.SetBlendShapeWeight(index, 0f);
                }
            }
        }
    }

    // -----------------------------------------------------------------------
    // Blendshape Auto-Detection
    // -----------------------------------------------------------------------

    /// <summary>
    /// Build the emotion → blendshape index dictionary.
    /// Uses Inspector overrides first, then auto-detects by scanning
    /// blendshape names for known VRM keywords.
    /// </summary>
    private void BuildEmotionDictionary()
    {
        // Initialize lists
        foreach (string emotion in AllEmotions)
        {
            _emotionToIndices[emotion] = new List<int>();
        }

        // Add overrides if set
        if (joyIndex >= 0) _emotionToIndices["Joy"].Add(joyIndex);
        if (angryIndex >= 0) _emotionToIndices["Angry"].Add(angryIndex);
        if (sorrowIndex >= 0) _emotionToIndices["Sorrow"].Add(sorrowIndex);
        if (funIndex >= 0) _emotionToIndices["Fun"].Add(funIndex);
        if (surprisedIndex >= 0) _emotionToIndices["Surprised"].Add(surprisedIndex);
        if (smugIndex >= 0) _emotionToIndices["Smug"].Add(smugIndex);
        if (despairIndex >= 0) _emotionToIndices["Despair"].Add(despairIndex);
        if (shyIndex >= 0) _emotionToIndices["Shy"].Add(shyIndex);
        if (confusedIndex >= 0) _emotionToIndices["Confused"].Add(confusedIndex);
        if (excitedIndex >= 0) _emotionToIndices["Excited"].Add(excitedIndex);
        if (loveIndex >= 0) _emotionToIndices["Love"].Add(loveIndex);

        // Auto-detect missing indices by scanning blendshape names
        Mesh mesh = faceMesh.sharedMesh;
        int count = mesh.blendShapeCount;
        Debug.Log($"[AvatarAction] Scanning {count} blendshapes for multi-expressions...");

        for (int i = 0; i < count; i++)
        {
            string name = mesh.GetBlendShapeName(i).ToLowerInvariant();

            foreach (var kvp in EmotionBlendshapes)
            {
                string emotion = kvp.Key;
                foreach (string keyword in kvp.Value)
                {
                    if (name.Contains(keyword.ToLowerInvariant()))
                    {
                        if (!_emotionToIndices[emotion].Contains(i))
                        {
                            _emotionToIndices[emotion].Add(i);
                            Debug.Log($"[AvatarAction] {emotion} + [{i}] {mesh.GetBlendShapeName(i)}");
                        }
                    }
                }
            }
        }

        // Report results
        int totalMapped = 0;
        foreach (string emotion in AllEmotions)
        {
            if (_emotionToIndices[emotion].Count > 0)
                totalMapped++;
        }
        Debug.Log($"[AvatarAction] Auto-detect complete: {totalMapped}/{AllEmotions.Length} expressions mapped.");
    }
}
