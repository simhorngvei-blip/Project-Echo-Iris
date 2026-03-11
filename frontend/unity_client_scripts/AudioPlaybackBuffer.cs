using System;
using System.Threading;
using UnityEngine;

/// <summary>
/// Echo-Iris — Audio Playback Buffer with FFT Vowel Analysis.
/// Ring-buffer-based audio playback with real-time frequency analysis
/// to estimate which vowel is being spoken for accurate lip-sync.
/// Attach to a GameObject with an AudioSource.
/// </summary>
[RequireComponent(typeof(AudioSource))]
public class AudioPlaybackBuffer : MonoBehaviour
{
    [Header("Settings")]
    [Tooltip("Output sample rate (must match server TTS_OUTPUT_SAMPLE_RATE)")]
    public int sampleRate = 44100;

    [Tooltip("Milliseconds of audio to buffer before starting playback")]
    public int preBufferMs = 150;

    [Tooltip("Ring buffer size in samples (default ~10 seconds at 44100)")]
    public int ringBufferSize = 441000;

    // --- Public state ---
    /// <summary>Current RMS energy (float 0-1).</summary>
    public float CurrentRMS { get; private set; }

    /// <summary>True when audio is actively playing.</summary>
    public bool IsPlaying => _isPlaying;

    // --- Vowel weights (0-1), computed from FFT in real-time ---
    /// <summary>あ (a) — jaw wide open.</summary>
    public float VowelA { get; private set; }
    /// <summary>い (i) — smile/stretch.</summary>
    public float VowelI { get; private set; }
    /// <summary>う (u) — pursed lips.</summary>
    public float VowelU { get; private set; }
    /// <summary>え (e) — slight open, front.</summary>
    public float VowelE { get; private set; }
    /// <summary>お (o) — round.</summary>
    public float VowelO { get; private set; }

    // --- Internal ---
    private AudioSource _audioSource;
    private float[] _ringBuffer;
    private int _writePos;
    private int _readPos;
    private bool _isPlaying;
    private bool _preBuffering;
    private int _preBufferSamples;

    // Lock-free synchronisation
    private int _availableSamples;

    // --- FFT analysis buffers ---
    private const int FFT_SIZE = 256;
    private readonly float[] _fftReal = new float[FFT_SIZE];
    private readonly float[] _fftImag = new float[FFT_SIZE];
    private readonly float[] _fftWindow = new float[FFT_SIZE];
    private readonly float[] _fftMagnitude = new float[FFT_SIZE / 2];
    private int _fftSampleCount;

    // Smoothed vowel outputs (to prevent jitter)
    private float _smoothA, _smoothI, _smoothU, _smoothE, _smoothO;
    private const float VOWEL_SMOOTH = 0.3f; // Lower = smoother, higher = snappier

    private void Awake()
    {
        _audioSource = GetComponent<AudioSource>();

        // Pre-compute Hann window
        for (int i = 0; i < FFT_SIZE; i++)
        {
            _fftWindow[i] = 0.5f * (1f - Mathf.Cos(2f * Mathf.PI * i / (FFT_SIZE - 1)));
        }

        Initialise();
    }

    /// <summary>Initialise (or re-initialise) the ring buffer.</summary>
    public void Initialise()
    {
        _ringBuffer = new float[ringBufferSize];
        _writePos = 0;
        _readPos = 0;
        _availableSamples = 0;
        _isPlaying = false;
        _preBuffering = true;
        _preBufferSamples = (sampleRate * preBufferMs) / 1000;
        CurrentRMS = 0f;
        VowelA = 0f; VowelI = 0f; VowelU = 0f; VowelE = 0f; VowelO = 0f;
        _smoothA = 0f; _smoothI = 0f; _smoothU = 0f; _smoothE = 0f; _smoothO = 0f;
        _fftSampleCount = 0;

        _audioSource.loop = true;
        _audioSource.clip = AudioClip.Create(
            "Echo-Iris_Stream",
            ringBufferSize,
            1, // mono
            sampleRate,
            false
        );
        _audioSource.Play();
    }

    /// <summary>
    /// Enqueue PCM 16-bit LE audio data into the ring buffer.
    /// Called from the main thread.
    /// </summary>
    public void EnqueuePCM(byte[] pcmData, float rms)
    {
        int sampleCount = pcmData.Length / 2;
        for (int i = 0; i < sampleCount; i++)
        {
            short val = (short)(pcmData[i * 2] | (pcmData[i * 2 + 1] << 8));
            float sample = val / 32768f;

            _ringBuffer[_writePos] = sample;
            _writePos = (_writePos + 1) % ringBufferSize;
        }

        Interlocked.Add(ref _availableSamples, sampleCount);

        if (_preBuffering && Interlocked.CompareExchange(ref _availableSamples, 0, 0) >= _preBufferSamples)
        {
            _preBuffering = false;
            _isPlaying = true;
        }
    }

    /// <summary>Reset the buffer.</summary>
    public void Reset()
    {
        _writePos = 0;
        _readPos = 0;
        Interlocked.Exchange(ref _availableSamples, 0);
        _isPlaying = false;
        _preBuffering = true;
        CurrentRMS = 0f;
        VowelA = 0f; VowelI = 0f; VowelU = 0f; VowelE = 0f; VowelO = 0f;
        _smoothA = 0f; _smoothI = 0f; _smoothU = 0f; _smoothE = 0f; _smoothO = 0f;
        _fftSampleCount = 0;
        if (_ringBuffer != null)
            Array.Clear(_ringBuffer, 0, _ringBuffer.Length);
    }

    /// <summary>
    /// Unity audio thread callback — reads from ring buffer and runs FFT analysis.
    /// </summary>
    private void OnAudioFilterRead(float[] data, int channels)
    {
        if (!_isPlaying || _ringBuffer == null)
        {
            Array.Clear(data, 0, data.Length);
            CurrentRMS = 0f;
            VowelA = 0f; VowelI = 0f; VowelU = 0f; VowelE = 0f; VowelO = 0f;
            return;
        }

        int samplesToRead = data.Length / channels;
        int available = Interlocked.CompareExchange(ref _availableSamples, 0, 0);

        if (available < samplesToRead)
        {
            Array.Clear(data, 0, data.Length);
            CurrentRMS = 0f;
            if (available == 0 && !_preBuffering)
            {
                _isPlaying = false;
                _preBuffering = true;
                VowelA = 0f; VowelI = 0f; VowelU = 0f; VowelE = 0f; VowelO = 0f;
            }
            return;
        }

        float sumSquares = 0f;

        for (int i = 0; i < samplesToRead; i++)
        {
            float sample = _ringBuffer[_readPos];
            _readPos = (_readPos + 1) % ringBufferSize;

            sumSquares += sample * sample;

            // Feed the FFT accumulator
            if (_fftSampleCount < FFT_SIZE)
            {
                _fftReal[_fftSampleCount] = sample * _fftWindow[_fftSampleCount];
                _fftSampleCount++;
            }

            // When we have enough samples, run FFT and estimate vowels
            if (_fftSampleCount >= FFT_SIZE)
            {
                Array.Clear(_fftImag, 0, FFT_SIZE);
                FFT(_fftReal, _fftImag, FFT_SIZE);
                ComputeMagnitudes();
                EstimateVowels();
                _fftSampleCount = 0;
            }

            // Write to all channels
            for (int ch = 0; ch < channels; ch++)
            {
                data[i * channels + ch] = sample;
            }
        }

        Interlocked.Add(ref _availableSamples, -samplesToRead);

        if (samplesToRead > 0)
        {
            CurrentRMS = Mathf.Sqrt(sumSquares / samplesToRead);
        }
    }

    // =========================================================================
    // FFT — Radix-2 Cooley-Tukey (in-place, iterative)
    // =========================================================================

    private static void FFT(float[] real, float[] imag, int n)
    {
        // Bit-reversal permutation
        int j = 0;
        for (int i = 0; i < n - 1; i++)
        {
            if (i < j)
            {
                float tr = real[i]; real[i] = real[j]; real[j] = tr;
                float ti = imag[i]; imag[i] = imag[j]; imag[j] = ti;
            }
            int k = n >> 1;
            while (k <= j) { j -= k; k >>= 1; }
            j += k;
        }

        // Butterfly passes
        for (int len = 2; len <= n; len <<= 1)
        {
            int half = len >> 1;
            float angle = -2f * Mathf.PI / len;
            float wR = Mathf.Cos(angle);
            float wI = Mathf.Sin(angle);

            for (int i = 0; i < n; i += len)
            {
                float curR = 1f, curI = 0f;
                for (int jj = 0; jj < half; jj++)
                {
                    int a = i + jj;
                    int b = a + half;
                    float tR = curR * real[b] - curI * imag[b];
                    float tI = curR * imag[b] + curI * real[b];
                    real[b] = real[a] - tR;
                    imag[b] = imag[a] - tI;
                    real[a] += tR;
                    imag[a] += tI;
                    float newR = curR * wR - curI * wI;
                    curI = curR * wI + curI * wR;
                    curR = newR;
                }
            }
        }
    }

    // =========================================================================
    // Frequency analysis — band energy → vowel weights
    // =========================================================================

    private void ComputeMagnitudes()
    {
        for (int i = 0; i < FFT_SIZE / 2; i++)
        {
            _fftMagnitude[i] = Mathf.Sqrt(_fftReal[i] * _fftReal[i] + _fftImag[i] * _fftImag[i]);
        }
    }

    /// <summary>
    /// Map frequency band energies to Japanese vowel weights.
    ///
    /// At 44100 Hz with 256-point FFT, each bin = 44100/256 ≈ 172 Hz.
    ///
    /// Formant bands:
    ///   Band 1 (Low F1):   172-516 Hz  → bins 1-3   — jaw openness (low)
    ///   Band 2 (High F1):  516-1032 Hz → bins 3-6   — jaw openness (high)
    ///   Band 3 (Low F2):   860-1720 Hz → bins 5-10  — tongue back
    ///   Band 4 (High F2): 1720-3100 Hz → bins 10-18 — tongue front
    ///
    /// Vowel mapping:
    ///   あ (a): High F1 (band2 dominant), moderate F2
    ///   い (i): Low F1, very high F2 (band4 dominant)
    ///   う (u): Low F1, low F2 (band1 only, everything else low)
    ///   え (e): Mid F1 (band2 moderate), high F2 (band4)
    ///   お (o): Mid F1 (band2), low F2 (band3 moderate, band4 low)
    /// </summary>
    private void EstimateVowels()
    {
        // ─── Non-overlapping frequency bands ───
        // At 44100 Hz with 256-point FFT: bin width = 172.27 Hz
        float lowBand  = BandEnergy(1,  4);   //  172 -  688 Hz  (F1 region)
        float midBand  = BandEnergy(5,  9);   //  861 - 1550 Hz  (upper F1 / low F2)
        float highBand = BandEnergy(10, 20);  // 1723 - 3445 Hz  (F2 region)

        float total = lowBand + midBand + highBand + 0.0001f;

        // Jaw openness: how much energy is in the mid band (F1 > 500Hz = open jaw)
        float jawOpen = midBand / total;
        // Tongue front/back: ratio of high vs low energy
        float tongueForward = highBand / (lowBand + highBand + 0.0001f);
        // Overall brightness
        float brightness = highBand / total;

        // ─── Vowel scoring using jaw + tongue position ───
        // A: jaw very open, tongue neutral    → high midBand, moderate everywhere
        // I: jaw closed, tongue very forward   → low midBand, very high highBand
        // U: jaw closed, tongue very back      → low midBand, very high lowBand
        // E: jaw moderately open, tongue forward → moderate midBand, high highBand
        // O: jaw moderately open, tongue back   → moderate midBand, high lowBand

        float rawA = jawOpen * 2.5f;
        float rawI = brightness * (1f - jawOpen) * 3.0f;
        float rawU = (lowBand / total) * (1f - brightness) * (1f - jawOpen) * 4.0f;
        float rawE = jawOpen * tongueForward * 2.5f;
        float rawO = jawOpen * (1f - tongueForward) * 2.5f;

        // Normalize so they sum to ~1.0
        float sum = rawA + rawI + rawU + rawE + rawO + 0.0001f;
        rawA /= sum;
        rawI /= sum;
        rawU /= sum;
        rawE /= sum;
        rawO /= sum;

        // Gate: if overall energy is too low, silence everything
        float energy = total;
        float gate = Mathf.Clamp01(energy * 20f); // ramp up from silence

        rawA *= gate;
        rawI *= gate;
        rawU *= gate;
        rawE *= gate;
        rawO *= gate;

        // Smooth to prevent jitter
        _smoothA += (rawA - _smoothA) * VOWEL_SMOOTH;
        _smoothI += (rawI - _smoothI) * VOWEL_SMOOTH;
        _smoothU += (rawU - _smoothU) * VOWEL_SMOOTH;
        _smoothE += (rawE - _smoothE) * VOWEL_SMOOTH;
        _smoothO += (rawO - _smoothO) * VOWEL_SMOOTH;

        VowelA = _smoothA;
        VowelI = _smoothI;
        VowelU = _smoothU;
        VowelE = _smoothE;
        VowelO = _smoothO;
    }

    /// <summary>Sum magnitudes in a frequency bin range.</summary>
    private float BandEnergy(int fromBin, int toBin)
    {
        float sum = 0f;
        toBin = Mathf.Min(toBin, FFT_SIZE / 2 - 1);
        for (int i = fromBin; i <= toBin; i++)
        {
            sum += _fftMagnitude[i];
        }
        return sum;
    }
}
