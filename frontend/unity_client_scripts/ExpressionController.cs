using UnityEngine;

/// <summary>
/// Echo-Iris — Expression Controller.
/// Receives emotion strings from the Audio WebSocket and smoothly transitions
/// the VRM avatar's facial blendshapes to match the AI's current emotion.
///
/// Supported emotions: Neutral, Joy, Angry, Sorrow, Fun, Surprised.
///
/// Attach to the same GameObject as AvatarAnimationController and assign
/// the SkinnedMeshRenderer that contains the facial blendshapes.
/// </summary>
public class ExpressionController : MonoBehaviour
{
    [Header("References")]
    [Tooltip("The avatar's SkinnedMeshRenderer containing facial expression blendshapes")]
    public SkinnedMeshRenderer faceMesh;

    [Tooltip("Reference to the AudioWebSocketManager (subscribes to OnEmotionReceived)")]
    public AudioWebSocketManager audioManager;

    [Tooltip("Reference to the AudioPlaybackBuffer (to detect when audio stops)")]
    public AudioPlaybackBuffer playbackBuffer;

    [Header("Tuning")]
    [Tooltip("Speed of expression transitions (higher = faster)")]
    public float transitionSpeed = 8f;

    [Tooltip("Maximum blendshape weight for expressions (0-100)")]
    public float maxWeight = 80f;

    [Tooltip("Seconds after audio ends to hold the expression before fading")]
    public float holdDuration = 1.0f;

    [Header("Blendshape Indices (set to -1 to auto-detect)")]
    public int joyIndex = -1;
    public int angryIndex = -1;
    public int sorrowIndex = -1;
    public int funIndex = -1;
    public int surprisedIndex = -1;

    // Internal state
    private string _currentEmotion = "Neutral";
    private string _targetEmotion = "Neutral";
    private float _holdTimer;
    private bool _wasPlaying;

    // Current smooth weights
    private float _wJoy, _wAngry, _wSorrow, _wFun, _wSurprised;

    // Auto-detect keywords for common VRM blendshapes
    private static readonly (string keyword, string emotion)[] BlendshapeKeywords = new (string, string)[]
    {
        ("joy", "Joy"), ("happy", "Joy"), ("smile", "Joy"),
        ("angry", "Angry"), ("anger", "Angry"),
        ("sorrow", "Sorrow"), ("sad", "Sorrow"),
        ("fun", "Fun"), ("excited", "Fun"),
        ("surprise", "Surprised"), ("surprised", "Surprised"),
    };

    private void Start()
    {
        if (faceMesh != null)
        {
            AutoDetectBlendshapes();
        }
        else
        {
            Debug.LogWarning("[Expression] No SkinnedMeshRenderer assigned!");
        }
    }

    private void OnEnable()
    {
        if (audioManager != null)
        {
            audioManager.OnEmotionReceived += HandleEmotionReceived;
            audioManager.OnAudioStreamEnd += HandleAudioEnd;
        }
    }

    private void OnDisable()
    {
        if (audioManager != null)
        {
            audioManager.OnEmotionReceived -= HandleEmotionReceived;
            audioManager.OnAudioStreamEnd -= HandleAudioEnd;
        }
    }

    /// <summary>Set the target emotion from the WebSocket event.</summary>
    public void HandleEmotionReceived(string emotion)
    {
        _targetEmotion = emotion ?? "Neutral";
        _holdTimer = 0f;
        Debug.Log($"[Expression] Emotion received: {_targetEmotion}");
    }

    /// <summary>When audio ends, start the hold timer before fading to Neutral.</summary>
    private void HandleAudioEnd()
    {
        _holdTimer = holdDuration;
    }

    private void Update()
    {
        // After audio ends, hold the expression briefly, then fade to Neutral
        if (playbackBuffer != null && !playbackBuffer.IsPlaying)
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

        // Compute target weights
        float tJoy = _targetEmotion == "Joy" ? maxWeight : 0f;
        float tAngry = _targetEmotion == "Angry" ? maxWeight : 0f;
        float tSorrow = _targetEmotion == "Sorrow" ? maxWeight : 0f;
        float tFun = _targetEmotion == "Fun" ? maxWeight : 0f;
        float tSurprised = _targetEmotion == "Surprised" ? maxWeight : 0f;

        // Smooth interpolation
        float dt = Time.deltaTime * transitionSpeed;
        _wJoy = Mathf.Lerp(_wJoy, tJoy, dt);
        _wAngry = Mathf.Lerp(_wAngry, tAngry, dt);
        _wSorrow = Mathf.Lerp(_wSorrow, tSorrow, dt);
        _wFun = Mathf.Lerp(_wFun, tFun, dt);
        _wSurprised = Mathf.Lerp(_wSurprised, tSurprised, dt);

        // Apply to mesh
        if (faceMesh != null)
        {
            if (joyIndex >= 0) faceMesh.SetBlendShapeWeight(joyIndex, _wJoy);
            if (angryIndex >= 0) faceMesh.SetBlendShapeWeight(angryIndex, _wAngry);
            if (sorrowIndex >= 0) faceMesh.SetBlendShapeWeight(sorrowIndex, _wSorrow);
            if (funIndex >= 0) faceMesh.SetBlendShapeWeight(funIndex, _wFun);
            if (surprisedIndex >= 0) faceMesh.SetBlendShapeWeight(surprisedIndex, _wSurprised);
        }

        _currentEmotion = _targetEmotion;
    }

    /// <summary>Scan the mesh for VRM expression blendshapes by keyword.</summary>
    private void AutoDetectBlendshapes()
    {
        Mesh mesh = faceMesh.sharedMesh;
        int count = mesh.blendShapeCount;

        Debug.Log($"[Expression] Scanning {count} blendshapes for expressions...");

        for (int i = 0; i < count; i++)
        {
            string name = mesh.GetBlendShapeName(i).ToLowerInvariant();

            // Skip already assigned
            foreach (var (keyword, emotion) in BlendshapeKeywords)
            {
                if (!name.Contains(keyword)) continue;

                switch (emotion)
                {
                    case "Joy": if (joyIndex < 0) { joyIndex = i; Debug.Log($"[Expression] Joy → [{i}] {mesh.GetBlendShapeName(i)}"); } break;
                    case "Angry": if (angryIndex < 0) { angryIndex = i; Debug.Log($"[Expression] Angry → [{i}] {mesh.GetBlendShapeName(i)}"); } break;
                    case "Sorrow": if (sorrowIndex < 0) { sorrowIndex = i; Debug.Log($"[Expression] Sorrow → [{i}] {mesh.GetBlendShapeName(i)}"); } break;
                    case "Fun": if (funIndex < 0) { funIndex = i; Debug.Log($"[Expression] Fun → [{i}] {mesh.GetBlendShapeName(i)}"); } break;
                    case "Surprised": if (surprisedIndex < 0) { surprisedIndex = i; Debug.Log($"[Expression] Surprised → [{i}] {mesh.GetBlendShapeName(i)}"); } break;
                }
                break;
            }
        }

        int found = 0;
        if (joyIndex >= 0) found++;
        if (angryIndex >= 0) found++;
        if (sorrowIndex >= 0) found++;
        if (funIndex >= 0) found++;
        if (surprisedIndex >= 0) found++;

        Debug.Log($"[Expression] Auto-detect complete: {found}/5 expressions found.");
    }

    /// <summary>Force Neutral expression immediately.</summary>
    public void ResetExpression()
    {
        _targetEmotion = "Neutral";
        _wJoy = 0f; _wAngry = 0f; _wSorrow = 0f; _wFun = 0f; _wSurprised = 0f;
        if (faceMesh != null)
        {
            if (joyIndex >= 0) faceMesh.SetBlendShapeWeight(joyIndex, 0f);
            if (angryIndex >= 0) faceMesh.SetBlendShapeWeight(angryIndex, 0f);
            if (sorrowIndex >= 0) faceMesh.SetBlendShapeWeight(sorrowIndex, 0f);
            if (funIndex >= 0) faceMesh.SetBlendShapeWeight(funIndex, 0f);
            if (surprisedIndex >= 0) faceMesh.SetBlendShapeWeight(surprisedIndex, 0f);
        }
    }
}
