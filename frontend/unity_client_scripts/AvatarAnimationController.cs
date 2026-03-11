using UnityEngine;

/// <summary>
/// Echo-Iris — Avatar Animation Controller.
/// Drives the Animator based on roaming state, audio playback,
/// and trick commands from the WebSocket or random triggers.
/// 
/// Requires an Animator component with parameters:
///   - IsWalking (bool), IsTalking (bool), TrickIndex (int), DoTrick (trigger)
/// </summary>
[RequireComponent(typeof(Animator))]
public class AvatarAnimationController : MonoBehaviour
{
    [Header("References")]
    public DesktopRoamController roamController;
    public AudioPlaybackBuffer playbackBuffer;

    [Header("Animation Clips")]
    [Tooltip("Names of trick animation states in the Animator")]
    public string[] trickNames = { "Cartwheel", "Flip", "Wave", "Dance", "Spin" };

    [Header("Talking")]
    [Tooltip("RMS threshold to consider the avatar 'talking' (float 0-1)")]
    public float talkRmsThreshold = 0.01f;

    // --- Animator parameter hashes (cached for performance) ---
    private static readonly int IsWalking = Animator.StringToHash("IsWalking");
    private static readonly int IsTalking = Animator.StringToHash("IsTalking");
    private static readonly int TrickIndex = Animator.StringToHash("TrickIndex");
    private static readonly int DoTrick = Animator.StringToHash("DoTrick");

    private Animator _animator;
    private bool _isTalking;

    private void Awake()
    {
        _animator = GetComponent<Animator>();
    }

    private void OnEnable()
    {
        if (roamController != null)
        {
            roamController.OnStartWalking += HandleStartWalking;
            roamController.OnStopWalking += HandleStopWalking;
            roamController.OnTrickRequested += HandleRandomTrick;
        }
    }

    private void OnDisable()
    {
        if (roamController != null)
        {
            roamController.OnStartWalking -= HandleStartWalking;
            roamController.OnStopWalking -= HandleStopWalking;
            roamController.OnTrickRequested -= HandleRandomTrick;
        }
    }

    private void Update()
    {
        UpdateTalkingState();
    }

    // --- Public API ---

    /// <summary>
    /// Trigger a specific trick animation by name.
    /// Called from WebSocket commands.
    /// </summary>
    public void PlayTrick(string trickName)
    {
        int index = System.Array.IndexOf(trickNames, trickName);
        if (index < 0)
        {
            // Try case-insensitive match
            for (int i = 0; i < trickNames.Length; i++)
            {
                if (trickNames[i].Equals(trickName, System.StringComparison.OrdinalIgnoreCase))
                {
                    index = i;
                    break;
                }
            }
        }

        if (index >= 0)
        {
            PlayTrickByIndex(index);
        }
        else
        {
            Debug.LogWarning($"[Animation] Unknown trick: {trickName}");
        }
    }

    /// <summary>
    /// Trigger a trick animation by index.
    /// </summary>
    public void PlayTrickByIndex(int index)
    {
        if (index < 0 || index >= trickNames.Length) return;

        // Pause roaming during trick
        if (roamController != null)
            roamController.ForceIdle();

        _animator.SetBool(IsWalking, false);
        _animator.SetInteger(TrickIndex, index);
        _animator.SetTrigger(DoTrick);

        Debug.Log($"[Animation] Playing trick: {trickNames[index]}");
    }

    /// <summary>
    /// Trigger a random trick animation.
    /// </summary>
    public void PlayRandomTrick()
    {
        if (trickNames.Length == 0) return;
        int index = Random.Range(0, trickNames.Length);
        PlayTrickByIndex(index);
    }

    /// <summary>
    /// Handle animation command from WebSocket.
    /// Expected format: {"type":"animation","action":"trick","trick":"flip"}
    /// </summary>
    public void HandleAnimationCommand(string action, string param)
    {
        switch (action.ToLower())
        {
            case "trick":
                PlayTrick(param);
                break;
            case "emote":
                PlayTrick(param); // emotes use same system
                break;
            case "random_trick":
                PlayRandomTrick();
                break;
            case "idle":
                _animator.SetBool(IsWalking, false);
                _animator.SetBool(IsTalking, false);
                break;
            default:
                Debug.LogWarning($"[Animation] Unknown action: {action}");
                break;
        }
    }

    // --- Event handlers ---

    private void HandleStartWalking()
    {
        _animator.SetBool(IsWalking, true);
    }

    private void HandleStopWalking()
    {
        _animator.SetBool(IsWalking, false);
    }

    private void HandleRandomTrick()
    {
        PlayRandomTrick();
    }

    // --- Internal ---

    /// <summary>
    /// Check if audio is playing and update the talking animation state.
    /// </summary>
    private void UpdateTalkingState()
    {
        if (playbackBuffer == null) return;

        bool shouldTalk = playbackBuffer.IsPlaying &&
                          playbackBuffer.CurrentRMS > talkRmsThreshold;

        if (shouldTalk != _isTalking)
        {
            _isTalking = shouldTalk;
            _animator.SetBool(IsTalking, _isTalking);
        }
    }
}
