using UnityEngine;

/// <summary>
/// Echo-Iris — Desktop Roam Controller.
/// Translates screen resolution bounds into Unity world space and
/// autonomously moves the avatar to random positions along the
/// bottom of the screen.
/// 
/// Requires an orthographic camera.
/// </summary>
public class DesktopRoamController : MonoBehaviour
{
    public enum RoamState
    {
        Idle,
        PickingTarget,
        Walking,
        ArrivedIdle
    }

    [Header("References")]
    [Tooltip("The camera used to convert screen-to-world coordinates")]
    public Camera mainCamera;

    [Tooltip("Reference to the TransparentWindowManager for screen dimensions")]
    public TransparentWindowManager windowManager;

    [Header("Movement")]
    [Tooltip("Walk speed in world units per second")]
    public float walkSpeed = 3.0f;

    [Tooltip("Minimum idle time before next roam (seconds)")]
    public float idleMinTime = 2.0f;

    [Tooltip("Maximum idle time before next roam (seconds)")]
    public float idleMaxTime = 8.0f;

    [Tooltip("Pixel margin from screen edges")]
    public float screenMargin = 50f;

    [Tooltip("Probability (0-1) of performing a trick after arriving")]
    public float trickChance = 0.3f;

    [Header("Floor")]
    [Tooltip("Y offset from bottom of screen in world units")]
    public float floorYOffset = 0.5f;

    // --- Public state ---
    /// <summary>Current roaming state.</summary>
    public RoamState CurrentState { get; private set; } = RoamState.Idle;

    /// <summary>Normalized walk direction (-1 = left, 1 = right, 0 = idle).</summary>
    public float WalkDirection { get; private set; }

    /// <summary>True if the avatar just arrived and should consider a trick.</summary>
    public bool ShouldTrick { get; private set; }

    // --- Internal ---
    private float _worldMinX;
    private float _worldMaxX;
    private float _floorY;
    private Vector3 _targetPosition;
    private float _idleTimer;

    // --- Events ---
    public System.Action OnStartWalking;
    public System.Action OnStopWalking;
    public System.Action OnTrickRequested;

    private void Start()
    {
        if (mainCamera == null)
            mainCamera = Camera.main;

        CalculateWorldBounds();
        _idleTimer = Random.Range(idleMinTime, idleMaxTime);
        CurrentState = RoamState.Idle;
    }

    private void Update()
    {
        switch (CurrentState)
        {
            case RoamState.Idle:
                UpdateIdle();
                break;
            case RoamState.PickingTarget:
                PickTarget();
                break;
            case RoamState.Walking:
                UpdateWalking();
                break;
            case RoamState.ArrivedIdle:
                UpdateArrivedIdle();
                break;
        }
    }

    /// <summary>
    /// Force the avatar to walk to a specific screen position.
    /// Called externally (e.g., from WebSocket commands).
    /// </summary>
    public void WalkToScreenPosition(float screenX)
    {
        Vector3 worldPos = ScreenToWorld(screenX, screenMargin);
        _targetPosition = new Vector3(worldPos.x, _floorY, transform.position.z);
        TransitionTo(RoamState.Walking);
    }

    /// <summary>
    /// Force the avatar to stop and go idle immediately.
    /// </summary>
    public void ForceIdle()
    {
        WalkDirection = 0f;
        _idleTimer = Random.Range(idleMinTime, idleMaxTime);
        TransitionTo(RoamState.Idle);
        OnStopWalking?.Invoke();
    }

    // --- State handlers ---

    private void UpdateIdle()
    {
        WalkDirection = 0f;
        _idleTimer -= Time.deltaTime;

        if (_idleTimer <= 0f)
        {
            TransitionTo(RoamState.PickingTarget);
        }
    }

    private void PickTarget()
    {
        // Random X within screen bounds (with margin)
        float randomX = Random.Range(_worldMinX, _worldMaxX);
        _targetPosition = new Vector3(randomX, _floorY, transform.position.z);

        // Set walk direction
        WalkDirection = Mathf.Sign(_targetPosition.x - transform.position.x);

        // Flip avatar to face walk direction
        Vector3 scale = transform.localScale;
        scale.x = Mathf.Abs(scale.x) * (WalkDirection < 0 ? -1f : 1f);
        transform.localScale = scale;

        TransitionTo(RoamState.Walking);
        OnStartWalking?.Invoke();
    }

    private void UpdateWalking()
    {
        // Move towards target
        Vector3 pos = transform.position;
        pos = Vector3.MoveTowards(pos, _targetPosition, walkSpeed * Time.deltaTime);
        transform.position = pos;

        // Check if arrived
        float dist = Mathf.Abs(pos.x - _targetPosition.x);
        if (dist < 0.05f)
        {
            WalkDirection = 0f;
            ShouldTrick = Random.value < trickChance;
            TransitionTo(RoamState.ArrivedIdle);
            OnStopWalking?.Invoke();

            if (ShouldTrick)
            {
                OnTrickRequested?.Invoke();
            }
        }
    }

    private void UpdateArrivedIdle()
    {
        _idleTimer -= Time.deltaTime;
        if (_idleTimer <= 0f)
        {
            ShouldTrick = false;
            TransitionTo(RoamState.PickingTarget);
        }
    }

    private void TransitionTo(RoamState newState)
    {
        CurrentState = newState;

        if (newState == RoamState.ArrivedIdle || newState == RoamState.Idle)
        {
            _idleTimer = Random.Range(idleMinTime, idleMaxTime);
        }
    }

    // --- Coordinate helpers ---

    /// <summary>
    /// Calculate world-space bounds from screen resolution.
    /// Uses the orthographic camera to map screen edges to world coords.
    /// </summary>
    private void CalculateWorldBounds()
    {
        if (mainCamera == null) return;

        // Screen corners in world space
        Vector3 bottomLeft = ScreenToWorld(screenMargin, screenMargin);
        Vector3 topRight = ScreenToWorld(
            Screen.width - screenMargin,
            Screen.height - screenMargin);

        _worldMinX = bottomLeft.x;
        _worldMaxX = topRight.x;
        _floorY = bottomLeft.y + floorYOffset;

        // Set initial position on the floor
        Vector3 pos = transform.position;
        pos.y = _floorY;
        transform.position = pos;

        Debug.Log($"[Roam] World bounds: X=[{_worldMinX:F2}, {_worldMaxX:F2}], floor Y={_floorY:F2}");
    }

    /// <summary>Convert screen pixel coordinates to world position.</summary>
    private Vector3 ScreenToWorld(float screenX, float screenY)
    {
        // For orthographic camera, z doesn't matter much — use camera distance
        float z = Mathf.Abs(mainCamera.transform.position.z);
        return mainCamera.ScreenToWorldPoint(new Vector3(screenX, screenY, z));
    }
}
