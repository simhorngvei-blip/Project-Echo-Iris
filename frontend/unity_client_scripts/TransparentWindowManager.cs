using System;
using System.Runtime.InteropServices;
using UnityEngine;

/// <summary>
/// Echo-Iris — Transparent Window Manager.
/// Uses Windows API P/Invoke to make the Unity window borderless, transparent,
/// always-on-top, and click-through on transparent areas.
/// 
/// Attach to a root GameObject. Requires:
///   - Camera clear flags = Solid Color, background = (0,0,0,0)
///   - Player Settings: "Use DXGI Flip Model Swapchain" = OFF
/// </summary>
public class TransparentWindowManager : MonoBehaviour
{
    [Header("Settings")]
    [Tooltip("Layer mask for the avatar (for click-through raycasting)")]
    public LayerMask avatarLayer;

    [Tooltip("Enable click-through on transparent areas")]
    public bool enableClickThrough = true;

#if (UNITY_STANDALONE_WIN || UNITY_EDITOR_WIN) && !UNITY_WEBGL

    // -- Win32 constants --
    private const int GWL_STYLE = -16;
    private const int GWL_EXSTYLE = -20;

    private const uint WS_POPUP = 0x80000000;
    private const uint WS_VISIBLE = 0x10000000;

    private const uint WS_EX_TOPMOST = 0x00000008;
    private const uint WS_EX_LAYERED = 0x00080000;
    private const uint WS_EX_TRANSPARENT = 0x00000020;

    private const int LWA_COLORKEY = 0x00000001;

    private const int HWND_TOPMOST = -1;
    private const uint SWP_SHOWWINDOW = 0x0040;
    private const uint SWP_NOSIZE = 0x0001;
    private const uint SWP_NOMOVE = 0x0002;

    private const int SM_CXSCREEN = 0;
    private const int SM_CYSCREEN = 1;

    // -- P/Invoke declarations --

    [DllImport("user32.dll")]
    private static extern IntPtr GetActiveWindow();

    [DllImport("user32.dll")]
    private static extern int SetWindowLong(IntPtr hWnd, int nIndex, uint dwNewLong);

    [DllImport("user32.dll")]
    private static extern uint GetWindowLong(IntPtr hWnd, int nIndex);

    [DllImport("user32.dll")]
    private static extern bool SetWindowPos(
        IntPtr hWnd, IntPtr hWndInsertAfter,
        int X, int Y, int cx, int cy, uint uFlags);

    [DllImport("user32.dll")]
    private static extern bool SetLayeredWindowAttributes(
        IntPtr hWnd, uint crKey, byte bAlpha, uint dwFlags);

    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int nIndex);

    [StructLayout(LayoutKind.Sequential)]
    private struct MARGINS
    {
        public int left, right, top, bottom;
    }

    [DllImport("dwmapi.dll")]
    private static extern int DwmExtendFrameIntoClientArea(IntPtr hWnd, ref MARGINS margins);

    // -- State --
    private IntPtr _hwnd;
    private Camera _mainCamera;
    private bool _isClickThrough;

    /// <summary>Screen width in pixels.</summary>
    public int ScreenWidth { get; private set; }

    /// <summary>Screen height in pixels.</summary>
    public int ScreenHeight { get; private set; }

    private void Start()
    {
#if !UNITY_EDITOR
        _mainCamera = Camera.main;
        _hwnd = GetActiveWindow();

        ScreenWidth = GetSystemMetrics(SM_CXSCREEN);
        ScreenHeight = GetSystemMetrics(SM_CYSCREEN);

        MakeTransparent();

        Debug.Log($"[TransparentWindow] Window made transparent — {ScreenWidth}x{ScreenHeight}");
#else
        ScreenWidth = Screen.width;
        ScreenHeight = Screen.height;
        Debug.Log("[TransparentWindow] Running in Editor — transparency disabled");
#endif
    }

    private void Update()
    {
#if !UNITY_EDITOR
        if (enableClickThrough)
            UpdateClickThrough();
#endif
    }

    /// <summary>
    /// Apply all window modifications: borderless, transparent, always-on-top.
    /// </summary>
    private void MakeTransparent()
    {
        // 1. Remove borders — set to popup style
        SetWindowLong(_hwnd, GWL_STYLE, WS_POPUP | WS_VISIBLE);

        // 2. Set extended styles: layered + topmost
        uint exStyle = WS_EX_TOPMOST | WS_EX_LAYERED;
        if (enableClickThrough)
            exStyle |= WS_EX_TRANSPARENT;
        SetWindowLong(_hwnd, GWL_EXSTYLE, exStyle);

        // 3. Color key transparency — black (0,0,0) pixels become transparent
        SetLayeredWindowAttributes(_hwnd, 0x00000000, 255, LWA_COLORKEY);

        // 4. Extend glass frame for full window transparency
        MARGINS margins = new MARGINS { left = -1, right = -1, top = -1, bottom = -1 };
        DwmExtendFrameIntoClientArea(_hwnd, ref margins);

        // 5. Position: full screen, always on top
        SetWindowPos(
            _hwnd, (IntPtr)HWND_TOPMOST,
            0, 0, ScreenWidth, ScreenHeight,
            SWP_SHOWWINDOW);

        // 6. Ensure camera renders with transparent background
        if (_mainCamera != null)
        {
            _mainCamera.clearFlags = CameraClearFlags.SolidColor;
            _mainCamera.backgroundColor = new Color(0f, 0f, 0f, 0f);
        }
    }

    /// <summary>
    /// Per-frame click-through toggle: if the mouse is over the avatar,
    /// remove WS_EX_TRANSPARENT so the window catches the click.
    /// Otherwise, add it back so clicks pass to the desktop.
    /// </summary>
    private void UpdateClickThrough()
    {
        if (_mainCamera == null) return;

        bool overAvatar = false;

        Ray ray = _mainCamera.ScreenPointToRay(Input.mousePosition);
        if (Physics.Raycast(ray, out RaycastHit hit, 100f, avatarLayer))
        {
            overAvatar = true;
        }

        if (overAvatar && _isClickThrough)
        {
            // Mouse is over avatar — make window receive clicks
            uint exStyle = GetWindowLong(_hwnd, GWL_EXSTYLE);
            exStyle &= ~WS_EX_TRANSPARENT;
            SetWindowLong(_hwnd, GWL_EXSTYLE, exStyle);
            _isClickThrough = false;
        }
        else if (!overAvatar && !_isClickThrough)
        {
            // Mouse is NOT over avatar — make click-through
            uint exStyle = GetWindowLong(_hwnd, GWL_EXSTYLE);
            exStyle |= WS_EX_TRANSPARENT;
            SetWindowLong(_hwnd, GWL_EXSTYLE, exStyle);
            _isClickThrough = true;
        }
    }

#else
    // Placeholder properties for non-Windows platforms
    public int ScreenWidth { get; private set; }
    public int ScreenHeight { get; private set; }

    private void Start()
    {
        ScreenWidth = Screen.width;
        ScreenHeight = Screen.height;
        Debug.LogWarning("[TransparentWindow] Not supported on this platform. Window transparency disabled.");
    }
#endif
}
