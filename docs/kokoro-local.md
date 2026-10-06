# Local English Kokoro speech

The optional `kokoro` package extra adds a local TTS adapter. It loads lazily and requires no API key. The provider is configured through `jarvis.core.config_writer`; it is not offered as an automatic-install card yet.

Install the Kokoro v1.0 full ONNX model as `kokoro-v1.0.onnx`, its `voices-v1.0.bin`, and the eSpeak NG data directory as `espeak-ng-data` under `~/.jarvis/models/kokoro`. An explicit `tts.model` may point to another directory. Model files are separate downloads and are not included in this repository.

Use `set_tts_provider("kokoro-local")` and select `am_michael` with `set_tts_voice`. Pin the response language to English with `set_reply_language("en")`. The adapter supports English only and rejects other languages. An empty `tts.fallback` keeps synthesis entirely local; any separately configured fallback is governed by the existing application factory.

The full model produced speech on macOS ARM. The quantized ConvInteger model did not work in that tested runtime. Windows and Linux have not been exercised. Missing optional dependencies or model files produce an explicit error when synthesis is requested; importing the base application does not load the engine.

Each adapter owns its native engine and rejects concurrent synthesis. A timeout or cancellation replaces the engine for the next request. It does not claim to terminate an already-running native call.

Validation: focused factory, protocol, language, PCM, busy-engine, timeout recovery, configuration and catalog tests; installed-adapter audio-to-Whisper-to-subscription-to-Kokoro file test. Live microphone, playback, gesture selection and interruption remain separate acceptance checks.
