using UnityEngine;

/// <summary>
/// A standalone tester script for Lip-sync and Expressions.
/// Attach this to your Avatar GameObject to test phonemes and expressions
/// without connecting to the server or recording your microphone.
/// </summary>
[RequireComponent(typeof(AudioSource))]
public class AvatarTester : MonoBehaviour
{
    [Header("Lip-Sync Testing")]
    [Tooltip("The avatar's SkinnedMeshRenderer")]
    public SkinnedMeshRenderer avatarMesh;
    
    [Tooltip("Index of the mouth-open blendshape (inspect your model)")]
    public int mouthOpenBlendshapeIndex = 0;
    
    [Tooltip("Drop an audio clip here to test lip-syncing")]
    public AudioClip testAudioClip;
    
    [Tooltip("Multiplier for the mouth opening")]
    public float rmsMultiplier = 3f;
    [Tooltip("Minimum RMS threshold for noise gate")]
    public float rmsThreshold = 0.01f;
    [Tooltip("Smoothing factor for mouth movements")]
    public float smoothSpeed = 12f;
    [Tooltip("Maximum weight of the blendshape (0-100)")]
    public float maxWeight = 80f;

    [Header("Expression Testing")]
    [Tooltip("Adjust these sliders to test other blendshapes manually")]
    [Range(0f, 100f)] public float joyWeight;
    public int joyBlendshapeIndex = -1;
    
    [Range(0f, 100f)] public float angryWeight;
    public int angryBlendshapeIndex = -1;

    [Range(0f, 100f)] public float sorrowWeight;
    public int sorrowBlendshapeIndex = -1;

    [Range(0f, 100f)] public float funWeight;
    public int funBlendshapeIndex = -1;

    // Internal Variables
    private AudioSource _audioSource;
    private float[] _samples = new float[256];
    private float _currentMouthWeight = 0f;

    private void Awake()
    {
        _audioSource = GetComponent<AudioSource>();
        if (avatarMesh == null)
        {
            avatarMesh = GetComponentInChildren<SkinnedMeshRenderer>();
        }
    }

    [ContextMenu("Play Test Audio")]
    public void PlayTestAudio()
    {
        if (testAudioClip != null)
        {
            _audioSource.clip = testAudioClip;
            _audioSource.loop = true;
            _audioSource.Play();
            Debug.Log($"Playing test audio: {testAudioClip.name}");
        }
        else
        {
            Debug.LogWarning("Please assign a Test Audio Clip first!");
        }
    }

    [ContextMenu("Stop Audio")]
    public void StopAudio()
    {
        _audioSource.Stop();
        _currentMouthWeight = 0f;
        if (avatarMesh != null) avatarMesh.SetBlendShapeWeight(mouthOpenBlendshapeIndex, 0f);
    }

    private void Update()
    {
        if (avatarMesh == null) return;

        // 1. Process Lip-Sync if audio is playing local clip
        if (_audioSource.isPlaying)
        {
            _audioSource.GetOutputData(_samples, 0);
            
            float sumSquares = 0f;
            for (int i = 0; i < _samples.Length; i++)
            {
                sumSquares += _samples[i] * _samples[i];
            }
            float rms = Mathf.Sqrt(sumSquares / _samples.Length);

            if (rms < rmsThreshold) rms = 0f;

            // Notice we don't divide by 32768f here because GetOutputData already returns floats [-1, 1]
            float targetWeight = Mathf.Clamp(rms * rmsMultiplier * 100f, 0f, maxWeight);
            _currentMouthWeight = Mathf.Lerp(_currentMouthWeight, targetWeight, Time.deltaTime * smoothSpeed);

            avatarMesh.SetBlendShapeWeight(mouthOpenBlendshapeIndex, _currentMouthWeight);
        }

        // 2. Process Manual Expression Sliders
        // (You can find out which index is which expression by looking at the Skinned Mesh Renderer)
        if (joyBlendshapeIndex >= 0) avatarMesh.SetBlendShapeWeight(joyBlendshapeIndex, joyWeight);
        if (angryBlendshapeIndex >= 0) avatarMesh.SetBlendShapeWeight(angryBlendshapeIndex, angryWeight);
        if (sorrowBlendshapeIndex >= 0) avatarMesh.SetBlendShapeWeight(sorrowBlendshapeIndex, sorrowWeight);
        if (funBlendshapeIndex >= 0) avatarMesh.SetBlendShapeWeight(funBlendshapeIndex, funWeight);
    }
}
