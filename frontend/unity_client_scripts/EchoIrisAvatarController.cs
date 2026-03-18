using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Echo-Iris — Unified Avatar Controller.
/// Consolidates Expression (Emotions), Lip-Sync (Phonemes), and Animation (Triggers/Talking State).
/// Supports VRM 0.x and VRM 1.0 standards.
/// </summary>
[RequireComponent(typeof(Animator))]
public class EchoIrisAvatarController : MonoBehaviour
{
    // -----------------------------------------------------------------------
    // 1. References
    // -----------------------------------------------------------------------

    [Header("Core References")]
    [Tooltip("The avatar's SkinnedMeshRenderer (for fallback blendshapes).")]
    public SkinnedMeshRenderer faceMesh;
    
    [Tooltip("Reference to the EchoIrisManager (orchestrator).")]
    public EchoIrisManager echoIrisManager;

    [Tooltip("Reference to the AudioPlaybackBuffer (for RMS and FFT data).")]
    public AudioPlaybackBuffer playbackBuffer;

    [Tooltip("Reference to DesktopRoamController (for mascot walk sync).")]
    public DesktopRoamController roamController;

    [Header("VRM Support (Auto-Detected)")]
    [Tooltip("For VRM 0.x avatars")]
    public VRM.VRMBlendShapeProxy vrm0Proxy;
#if USE_UNIVRM10
    [Tooltip("For VRM 1.0 avatars")]
    public UniVRM10.Vrm10Instance vrm1Instance;
#endif

    // -----------------------------------------------------------------------
    // 2. Settings
    // -----------------------------------------------------------------------

    [Header("Expression Tuning")]
    [Range(1f, 20f)] public float transitionSpeed = 8f;
    [Range(0f, 100f)] public float maxExpressionWeight = 80f;
    public float expressionHoldDuration = 1.0f;

    [Header("Lip-Sync Tuning")]
    public float lipSyncSmoothSpeed = 14f;
    public float lipSyncIntensity = 1.5f;
    [Range(0f, 100f)] public float maxLipWeight = 85f;
    public float rmsThreshold = 0.003f;

    [Header("Animation Tuning")]
    public float talkRmsThreshold = 0.01f;
    [Tooltip("Names of trick animation states in the Animator")]
    public string[] trickNames = { "Cartwheel", "Flip", "Wave", "Dance", "Spin" };

    [Header("Manual Index Overrides (-1 for Auto-Detect)")]
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
    [Space]
    public int indexA = -1; // あ
    public int indexI = -1; // い
    public int indexU = -1; // う
    public int indexE = -1; // え
    public int indexO = -1; // お

    // -----------------------------------------------------------------------
    // 3. Private State
    // -----------------------------------------------------------------------

    private Animator _animator;
    private Dictionary<string, List<int>> _emotionToIndices = new Dictionary<string, List<int>>();
    private Dictionary<string, float> _currentWeights = new Dictionary<string, float>();
    private string _targetEmotion = "Neutral";
    private float _holdTimer;
    private bool _manualOverride;
    private bool _isTalking;

    // Smooth vowel weights
    private float _vA, _vI, _vU, _vE, _vO;

    private static readonly int IsWalking = Animator.StringToHash("IsWalking");
    private static readonly int IsTalking = Animator.StringToHash("IsTalking");
    private static readonly int TrickIndex = Animator.StringToHash("TrickIndex");
    private static readonly int DoTrick = Animator.StringToHash("DoTrick");

    private static readonly Dictionary<string, string[]> EmotionKeywords = new Dictionary<string, string[]>()
    {
        { "Joy", new[] { "笑い", "はう", "はわ", "joy", "smile", "happy" } },
        { "Angry", new[] { "怒り", "おこ", "チーク", "angry", "anger" } },
        { "Sorrow", new[] { "悲しい", "涙", "むう", "sorrow", "sad" } },
        { "Fun", new[] { "にこり", "fun", "excited", "cheerful" } },
        { "Surprised", new[] { "びっくり", "surprise", "surprised" } },
        { "Smug", new[] { "にやり", "smug", "smirk" } },
        { "Despair", new[] { "絶望", "despair", "shock" } },
        { "Shy", new[] { "チーク", "shy", "blush" } },
        { "Confused", new[] { "グルグル", "confused", "dizzy" } },
        { "Excited", new[] { "星瞳", "star" } },
        { "Love", new[] { "ハート瞳", "love", "heart" } }
    };

    private static readonly string[] Emotions = { 
        "Joy", "Angry", "Sorrow", "Fun", "Surprised",
        "Smug", "Despair", "Shy", "Confused", "Excited", "Love" 
    };

    private void Awake()
    {
        _animator = GetComponent<Animator>();
    }

    private void Start()
    {
        foreach (string e in Emotions) _currentWeights[e] = 0f;

        // Auto-detect VRM
        if (vrm0Proxy == null) vrm0Proxy = GetComponentInParent<VRM.VRMBlendShapeProxy>();
#if USE_UNIVRM10
        if (vrm1Instance == null) vrm1Instance = GetComponentInParent<UniVRM10.Vrm10Instance>();
#endif

        if (faceMesh != null)
        {
            BuildMappingDictionary();
        }

        // Subscriptions
        if (echoIrisManager != null && echoIrisManager.AudioManager != null)
        {
            echoIrisManager.AudioManager.OnEmotionReceived += HandleEmotionReceived;
            echoIrisManager.AudioManager.OnAnimationReceived += HandleAnimationReceived;
            echoIrisManager.AudioManager.OnAudioStreamEnd += HandleAudioEnd;
        }

        if (roamController != null)
        {
            roamController.OnStartWalking += () => _animator.SetBool(IsWalking, true);
            roamController.OnStopWalking += () => _animator.SetBool(IsWalking, false);
            roamController.OnTrickRequested += PlayRandomTrick;
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

    private void Update()
    {
        UpdateExpressions();
        UpdateLipSync();
        UpdateTalkingAnimation();
    }

    // -----------------------------------------------------------------------
    // 4. Expression Logic
    // -----------------------------------------------------------------------

    private void UpdateExpressions()
    {
        // Auto-fade
        if (!_manualOverride && playbackBuffer != null && !playbackBuffer.IsPlaying)
        {
            if (_holdTimer > 0f) _holdTimer -= Time.deltaTime;
            else if (_targetEmotion != "Neutral") _targetEmotion = "Neutral";
        }

        float dt = Time.deltaTime * transitionSpeed;
        foreach (string e in Emotions)
        {
            float target = (_targetEmotion == e) ? maxExpressionWeight : 0f;
            _currentWeights[e] = Mathf.Lerp(_currentWeights[e], target, dt);
        }

        ApplyWeights();
    }

    private void ApplyWeights()
    {
#if USE_UNIVRM10
        if (vrm1Instance != null && vrm1Instance.Runtime != null)
        {
            var exp = vrm1Instance.Runtime.Expression;
            exp.SetWeight(UniVRM10.ExpressionKey.Happy, _currentWeights["Joy"] / 100f);
            exp.SetWeight(UniVRM10.ExpressionKey.Angry, _currentWeights["Angry"] / 100f);
            exp.SetWeight(UniVRM10.ExpressionKey.Sad, _currentWeights["Sorrow"] / 100f);
            exp.SetWeight(UniVRM10.ExpressionKey.Relaxed, _currentWeights["Fun"] / 100f);
            exp.SetWeight(UniVRM10.ExpressionKey.Surprised, _currentWeights["Surprised"] / 100f);

            exp.SetWeight(UniVRM10.ExpressionKey.CreateCustom("Smug"), _currentWeights["Smug"] / 100f);
            exp.SetWeight(UniVRM10.ExpressionKey.CreateCustom("Despair"), _currentWeights["Despair"] / 100f);
            exp.SetWeight(UniVRM10.ExpressionKey.CreateCustom("Shy"), _currentWeights["Shy"] / 100f);
            exp.SetWeight(UniVRM10.ExpressionKey.CreateCustom("Confused"), _currentWeights["Confused"] / 100f);
            exp.SetWeight(UniVRM10.ExpressionKey.CreateCustom("Love"), _currentWeights["Love"] / 100f);
            
            vrm1Instance.Runtime.Process();
            return;
        }
#endif
        if (vrm0Proxy != null)
        {
            vrm0Proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.Joy), _currentWeights["Joy"] / 100f);
            vrm0Proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.Angry), _currentWeights["Angry"] / 100f);
            vrm0Proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.Sorrow), _currentWeights["Sorrow"] / 100f);
            vrm0Proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.Fun), _currentWeights["Fun"] / 100f);
            vrm0Proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateUnknown("Smug"), _currentWeights["Smug"] / 100f);
            vrm0Proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateUnknown("Shy"), _currentWeights["Shy"] / 100f);
            // ... add others as needed
            return;
        }

        if (faceMesh != null)
        {
            foreach (var e in Emotions)
            {
                if (_emotionToIndices.TryGetValue(e, out var indices))
                {
                    foreach (int idx in indices) faceMesh.SetBlendShapeWeight(idx, _currentWeights[e]);
                }
            }
        }
    }

    // -----------------------------------------------------------------------
    // 5. Lip-Sync Logic
    // -----------------------------------------------------------------------

    private void UpdateLipSync()
    {
        if (playbackBuffer == null) return;
        float rms = playbackBuffer.CurrentRMS;

        if (rms < rmsThreshold)
        {
            LerpVowel(ref _vA, 0f, indexA); // あ
            LerpVowel(ref _vI, 0f, indexI); // い
            LerpVowel(ref _vU, 0f, indexU); // う
            LerpVowel(ref _vE, 0f, indexE); // え
            LerpVowel(ref _vO, 0f, indexO); // お
            return;
        }

        LerpVowel(ref _vA, playbackBuffer.VowelA * lipSyncIntensity, indexA);
        LerpVowel(ref _vI, playbackBuffer.VowelI * lipSyncIntensity, indexI);
        LerpVowel(ref _vU, playbackBuffer.VowelU * lipSyncIntensity, indexU);
        LerpVowel(ref _vE, playbackBuffer.VowelE * lipSyncIntensity, indexE);
        LerpVowel(ref _vO, playbackBuffer.VowelO * lipSyncIntensity, indexO);
    }

    private void LerpVowel(ref float current, float target, int blendIdx)
    {
        float targetWeight = Mathf.Clamp(target * 100f, 0f, maxLipWeight);
        current = Mathf.Lerp(current, targetWeight, Time.deltaTime * lipSyncSmoothSpeed);

#if USE_UNIVRM10
        if (vrm1Instance != null && vrm1Instance.Runtime != null)
        {
            float w = current / 100f;
            var exp = vrm1Instance.Runtime.Expression;
            if (blendIdx == indexA) exp.SetWeight(UniVRM10.ExpressionKey.Aa, w);
            else if (blendIdx == indexI) exp.SetWeight(UniVRM10.ExpressionKey.Ih, w);
            else if (blendIdx == indexU) exp.SetWeight(UniVRM10.ExpressionKey.Ou, w);
            else if (blendIdx == indexE) exp.SetWeight(UniVRM10.ExpressionKey.Ee, w);
            else if (blendIdx == indexO) exp.SetWeight(UniVRM10.ExpressionKey.Oh, w);
            return;
        }
#endif
        if (vrm0Proxy != null)
        {
            float w = current / 100f;
            if (blendIdx == indexA) vrm0Proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.A), w);
            else if (blendIdx == indexI) vrm0Proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.I), w);
            else if (blendIdx == indexU) vrm0Proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.U), w);
            else if (blendIdx == indexE) vrm0Proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.E), w);
            else if (blendIdx == indexO) vrm0Proxy.ImmediatelySetValue(VRM.BlendShapeKey.CreateFromPreset(VRM.BlendShapePreset.O), w);
            return;
        }

        if (faceMesh != null && blendIdx >= 0)
        {
            faceMesh.SetBlendShapeWeight(blendIdx, current);
        }
    }

    // -----------------------------------------------------------------------
    // 6. Animation Logic
    // -----------------------------------------------------------------------

    private void UpdateTalkingAnimation()
    {
        if (playbackBuffer == null) return;
        bool isTalking = playbackBuffer.IsPlaying && playbackBuffer.CurrentRMS > talkRmsThreshold;
        if (isTalking != _isTalking)
        {
            _isTalking = isTalking;
            _animator.SetBool(IsTalking, _isTalking);
        }
    }

    public void PlayTrick(string trickName)
    {
        int index = System.Array.FindIndex(trickNames, t => t.Equals(trickName, System.StringComparison.OrdinalIgnoreCase));
        if (index >= 0) PlayTrickByIndex(index);
    }

    public void PlayTrickByIndex(int index)
    {
        if (index < 0 || index >= trickNames.Length) return;
        if (roamController != null) roamController.ForceIdle();
        _animator.SetBool(IsWalking, false);
        _animator.SetInteger(TrickIndex, index);
        _animator.SetTrigger(DoTrick);
    }

    public void PlayRandomTrick() => PlayTrickByIndex(Random.Range(0, trickNames.Length));

    public void HandleAnimationReceived(string animation) => PlayTrick(animation);

    // -----------------------------------------------------------------------
    // 7. Event Handlers
    // -----------------------------------------------------------------------

    public void HandleEmotionReceived(string emotion)
    {
        _targetEmotion = string.IsNullOrEmpty(emotion) ? "Neutral" : emotion;
        _holdTimer = 0f;
        _manualOverride = (playbackBuffer == null || !playbackBuffer.IsPlaying);
        Debug.Log($"[Avatar] Emotion -> {_targetEmotion} (manual={_manualOverride})");
    }

    private void HandleAudioEnd()
    {
        _manualOverride = false;
        _holdTimer = expressionHoldDuration;
    }

    // -----------------------------------------------------------------------
    // 8. Auto-Detection
    // -----------------------------------------------------------------------

    private void BuildMappingDictionary()
    {
        foreach (string e in Emotions) _emotionToIndices[e] = new List<int>();

        // Apply overrides
        if (joyIndex >= 0) _emotionToIndices["Joy"].Add(joyIndex);
        if (angryIndex >= 0) _emotionToIndices["Angry"].Add(angryIndex);
        if (indexA < 0) indexA = 0; // Default or Scan

        Mesh m = faceMesh.sharedMesh;
        for (int i = 0; i < m.blendShapeCount; i++)
        {
            string name = m.GetBlendShapeName(i).ToLowerInvariant();
            foreach (var kvp in EmotionKeywords)
            {
                foreach (string kw in kvp.Value)
                {
                    if (name.Contains(kw) && !_emotionToIndices[kvp.Key].Contains(i))
                        _emotionToIndices[kvp.Key].Add(i);
                }
            }
            // Simple vowel scan
            if (indexA < 0 && (name == "あ" || name.Contains("mouth_a"))) indexA = i;
            if (indexI < 0 && (name == "い" || name.Contains("mouth_i"))) indexI = i;
            if (indexU < 0 && (name == "う" || name.Contains("mouth_u"))) indexU = i;
            if (indexE < 0 && (name == "え" || name.Contains("mouth_e"))) indexE = i;
            if (indexO < 0 && (name == "お" || name.Contains("mouth_o"))) indexO = i;
        }
    }
}
