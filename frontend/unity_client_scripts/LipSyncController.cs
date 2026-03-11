using UnityEngine;

/// <summary>
/// Echo-Iris — Vowel-Aware Lip-Sync Controller (v3 — FFT).
/// Reads per-vowel weights from AudioPlaybackBuffer's real-time FFT analysis
/// and drives each mouth blendshape (あ, い, う, え, お) independently.
/// </summary>
public class LipSyncController : MonoBehaviour
{
    [Header("Avatar")]
    [Tooltip("The avatar's SkinnedMeshRenderer that contains mouth blendshapes")]
    public SkinnedMeshRenderer avatarMesh;

    [Header("Audio Source")]
    [Tooltip("Reference to the AudioPlaybackBuffer (provides FFT vowel weights)")]
    public AudioPlaybackBuffer playbackBuffer;

    [Header("Tuning")]
    [Tooltip("How fast the mouth reacts (higher = snappier)")]
    public float smoothSpeed = 14f;

    [Tooltip("Overall intensity multiplier for mouth movement")]
    public float intensity = 1.5f;

    [Tooltip("Maximum blendshape weight per vowel (0-100)")]
    public float maxWeight = 85f;

    [Tooltip("Minimum RMS to activate any mouth movement (noise gate)")]
    public float rmsThreshold = 0.003f;

    [Header("Manual Overrides (set to -1 to use auto-detect)")]
    public int indexA = -1;   // あ
    public int indexI = -1;   // い
    public int indexU = -1;   // う
    public int indexE = -1;   // え
    public int indexO = -1;   // お

    // Internal smooth values
    private float _weightA, _weightI, _weightU, _weightE, _weightO;

    // Auto-detect keyword pairs: (keyword, which vowel it maps to)
    // 'A'=0, 'I'=1, 'U'=2, 'E'=3, 'O'=4
    private static readonly (string keyword, int vowel)[] VowelKeywords = new (string, int)[]
    {
        // VRM / UniVRM (English)
        ("fcl_mth_a", 0), ("fcl_mth_i", 1), ("fcl_mth_u", 2), ("fcl_mth_e", 3), ("fcl_mth_o", 4),
        ("mouth_a", 0), ("mouth_i", 1), ("mouth_u", 2), ("mouth_e", 3), ("mouth_o", 4),
        ("viseme_aa", 0), ("viseme_ih", 1), ("viseme_ou", 2), ("viseme_ee", 3), ("viseme_oh", 4),
        ("vrc.v_aa", 0), ("vrc.v_ih", 1), ("vrc.v_ou", 2), ("vrc.v_ee", 3), ("vrc.v_oh", 4),
        ("jaw_open", 0), ("jawopen", 0), ("mouth_open", 0), ("mouthopen", 0),
    };

    // Japanese exact-match vowels
    private static readonly (string name, int vowel)[] JapaneseVowels = new (string, int)[]
    {
        ("あ", 0), ("い", 1), ("う", 2), ("え", 3), ("お", 4),
    };

    // Exclusion keywords — never match these
    private static readonly string[] ExcludeKeywords = new string[]
    {
        "eye", "brow", "brw", "cheek", "nose", "tongue",
        "まばたき", "ウインク", "目", "瞳", "瞼",
        "びっくり", "ジト", "ハイライト", "白目", "カメラ目線",
        "星", "ハート", "グルグル",
    };

    private void Start()
    {
        if (avatarMesh == null)
        {
            Debug.LogError("[LipSync] No SkinnedMeshRenderer assigned!");
            return;
        }

        AutoDetectVowelBlendshapes();

        int found = 0;
        if (indexA >= 0) found++;
        if (indexI >= 0) found++;
        if (indexU >= 0) found++;
        if (indexE >= 0) found++;
        if (indexO >= 0) found++;

        Debug.Log($"[LipSync] Vowel mapping: A={indexA}, I={indexI}, U={indexU}, E={indexE}, O={indexO} ({found}/5 found)");

        if (found == 0)
        {
            Debug.LogWarning("[LipSync] No vowel blendshapes found! Check the Console log above for the full list, " +
                             "then set the indices manually in the Inspector.");
        }
    }

    private void AutoDetectVowelBlendshapes()
    {
        Mesh mesh = avatarMesh.sharedMesh;
        int count = mesh.blendShapeCount;

        Debug.Log($"[LipSync] Scanning {count} blendshapes on '{avatarMesh.gameObject.name}'...");

        // Dump all blendshape names for manual identification
        string allNames = "";
        for (int i = 0; i < count; i++)
        {
            allNames += $"  [{i}] {mesh.GetBlendShapeName(i)}\n";
        }
        Debug.Log($"[LipSync] Full blendshape list:\n{allNames}");

        // Scan each blendshape
        for (int i = 0; i < count; i++)
        {
            string originalName = mesh.GetBlendShapeName(i);
            string nameLower = originalName.ToLowerInvariant().Trim();

            // Check exclusion list
            bool excluded = false;
            foreach (string ex in ExcludeKeywords)
            {
                if (nameLower.Contains(ex))
                {
                    excluded = true;
                    break;
                }
            }
            if (excluded) continue;

            // Try Japanese exact match first (most reliable for VRM models)
            foreach (var (jpName, vowel) in JapaneseVowels)
            {
                if (originalName.Trim() == jpName)
                {
                    AssignVowelIndex(vowel, i, originalName, jpName);
                    break;
                }
            }

            // Try English substring match
            foreach (var (keyword, vowel) in VowelKeywords)
            {
                if (nameLower.Contains(keyword))
                {
                    AssignVowelIndex(vowel, i, originalName, keyword);
                    break;
                }
            }
        }
    }

    private void AssignVowelIndex(int vowel, int blendshapeIndex, string name, string keyword)
    {
        string vowelName = vowel switch { 0 => "A(あ)", 1 => "I(い)", 2 => "U(う)", 3 => "E(え)", 4 => "O(お)", _ => "?" };

        // Only assign if not already set (first match wins)
        switch (vowel)
        {
            case 0: if (indexA < 0) { indexA = blendshapeIndex; Log(vowelName, blendshapeIndex, name, keyword); } break;
            case 1: if (indexI < 0) { indexI = blendshapeIndex; Log(vowelName, blendshapeIndex, name, keyword); } break;
            case 2: if (indexU < 0) { indexU = blendshapeIndex; Log(vowelName, blendshapeIndex, name, keyword); } break;
            case 3: if (indexE < 0) { indexE = blendshapeIndex; Log(vowelName, blendshapeIndex, name, keyword); } break;
            case 4: if (indexO < 0) { indexO = blendshapeIndex; Log(vowelName, blendshapeIndex, name, keyword); } break;
        }
    }

    private void Log(string vowel, int idx, string name, string keyword)
    {
        Debug.Log($"[LipSync] ✓ {vowel} → [{idx}] '{name}' (matched '{keyword}')");
    }

    private void Update()
    {
        if (avatarMesh == null || playbackBuffer == null) return;

        float rms = playbackBuffer.CurrentRMS;

        // Zero everything if below noise gate
        if (rms < rmsThreshold)
        {
            DriveVowel(ref _weightA, 0f, indexA);
            DriveVowel(ref _weightI, 0f, indexI);
            DriveVowel(ref _weightU, 0f, indexU);
            DriveVowel(ref _weightE, 0f, indexE);
            DriveVowel(ref _weightO, 0f, indexO);
            return;
        }

        // Read FFT-computed vowel weights from the audio buffer
        float a = playbackBuffer.VowelA * intensity;
        float i = playbackBuffer.VowelI * intensity;
        float u = playbackBuffer.VowelU * intensity;
        float e = playbackBuffer.VowelE * intensity;
        float o = playbackBuffer.VowelO * intensity;

        // Drive each vowel independently
        DriveVowel(ref _weightA, a, indexA);
        DriveVowel(ref _weightI, i, indexI);
        DriveVowel(ref _weightU, u, indexU);
        DriveVowel(ref _weightE, e, indexE);
        DriveVowel(ref _weightO, o, indexO);
    }

    private void DriveVowel(ref float current, float target, int blendshapeIdx)
    {
        if (blendshapeIdx < 0) return;

        float clamped = Mathf.Clamp(target * 100f, 0f, maxWeight);
        current = Mathf.Lerp(current, clamped, Time.deltaTime * smoothSpeed);
        avatarMesh.SetBlendShapeWeight(blendshapeIdx, current);
    }

    /// <summary>Immediately close all mouth shapes.</summary>
    public void ResetMouth()
    {
        _weightA = 0f; _weightI = 0f; _weightU = 0f; _weightE = 0f; _weightO = 0f;
        if (avatarMesh != null)
        {
            if (indexA >= 0) avatarMesh.SetBlendShapeWeight(indexA, 0f);
            if (indexI >= 0) avatarMesh.SetBlendShapeWeight(indexI, 0f);
            if (indexU >= 0) avatarMesh.SetBlendShapeWeight(indexU, 0f);
            if (indexE >= 0) avatarMesh.SetBlendShapeWeight(indexE, 0f);
            if (indexO >= 0) avatarMesh.SetBlendShapeWeight(indexO, 0f);
        }
    }
}
