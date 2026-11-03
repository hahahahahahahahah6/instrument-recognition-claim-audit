import ast
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from instrument_recognition_claim_audit.audit import audit, claims, evidence, main, GENERIC
from instrument_recognition_claim_audit.phrases import INSTRUMENT, NOINSTRUMENT

EXPECTED_POS = ('music instrument recognition', 'recognizes musical instruments', 'recognises musical instruments', 'identifies musical instruments', 'detects musical instruments', 'classifies musical instruments', 'predicts musical instruments', 'instrument recognition', 'musical instrument recognition', 'audio instrument recognition', 'instrument identification', 'musical instrument identification', 'identifies instruments in music', 'detects instruments in music', 'recognizes instruments in music', 'classifies instruments in music', 'identifies the instruments in a song', 'detects the instruments in a song', 'recognizes the instruments in a song', 'instrument detection', 'musical instrument detection', 'instrument classification', 'musical instrument classification', 'classifies music by instrument', 'classifies songs by instrument', 'classifies audio by instrument', 'detects music instruments', 'identifies music instruments', 'predicts music instruments', 'recognizes music instruments', 'labels music by instrument', 'tags music by instrument', 'determines musical instruments', 'determines the instruments in music', 'identifies an instrument', 'detects an instrument', 'recognizes an instrument', 'predicts an instrument', 'classifies an instrument', 'instrument recognition of music', 'instrument recognition of songs', 'automatic instrument recognition', 'automatic musical instrument recognition', 'song instrument recognition', 'song instrument identification', 'track instrument recognition', 'track instrument identification', 'audio instrument identification', 'identifies instrument', 'detects instrument')
EXPECTED_NEG = ('no musical instrument recognition', 'does not recognize musical instruments', 'does not recognise musical instruments', 'without musical instrument recognition', 'does not identify musical instruments', 'does not detect musical instruments', 'does not classify musical instruments', 'does not predict musical instruments', 'does not identify instruments in music', 'does not detect instruments in music', 'does not recognize instruments in music', 'no instrument recognition', 'does not recognize instruments', 'does not identify instruments', 'does not detect instruments', 'no instrument identification', 'does not classify music by instrument', 'does not detect music instruments', 'does not identify music instruments', 'musical instrument recognition not supported', 'instrument recognition not supported', 'no instrument detection', 'does not detect musical instrument', 'does not identify musical instrument')


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def put(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
        return p

    def cli(self, *args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = main([str(self.root), *args])
        return code, out.getvalue()

    def test_oracle(self):
        import instrument_recognition_claim_audit.phrases as module
        assignments = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(Path(module.__file__).read_text()).body if isinstance(n, ast.Assign)}
        self.assertEqual(assignments['INSTRUMENT'], EXPECTED_POS)
        self.assertEqual(assignments['NOINSTRUMENT'], EXPECTED_NEG)
        self.assertEqual(INSTRUMENT, EXPECTED_POS)
        self.assertEqual(NOINSTRUMENT, EXPECTED_NEG)
        self.assertEqual((len(INSTRUMENT), len(NOINSTRUMENT)), (50, 24))
        for phrase in EXPECTED_POS:
            self.assertEqual(claims(phrase), (True, False), phrase)
        for phrase in EXPECTED_NEG:
            self.assertEqual(claims(phrase), (False, True), phrase)

    def test_bad_good_denial(self):
        self.put('README.md', 'instrument recognition')
        self.assertEqual(self.cli()[0], 2)
        f = audit(self.root)['findings'][0]
        self.assertEqual((f['id'], f['severity']), ('documented-instrument-recognition-claim-false', 'HIGH'))
        self.put('app.py', 'engine.detect_instrument(audio)')
        self.assertEqual(self.cli()[0], 0)
        self.put('README.md', 'no instrument recognition')
        self.assertEqual(self.cli()[0], 2)
        f = audit(self.root)['findings'][0]
        self.assertEqual((f['id'], f['severity']), ('documented-no-instrument-recognition-claim-false', 'HIGH'))

    def test_no_source(self):
        self.put('README.md', 'no instrument recognition')
        self.assertEqual(audit(self.root)['verdict'], 'PASS')
        self.put('README.md', 'instrument recognition')
        self.assertEqual(self.cli()[0], 2)
        self.put('README.md', 'ordinary prose')
        self.assertEqual(self.cli()[0], 0)

    def test_test_only(self):
        self.put('README.md', 'instrument recognition')
        for name in ('tests/app.py', 'test_app.py', 'app_test.py'):
            with self.subTest(name=name):
                p = self.put(name, 'e.classify_instrument(x)')
                self.assertEqual(self.cli()[0], 0)
                self.assertEqual(audit(self.root)['findings'][0]['severity'], 'MEDIUM')
                self.assertEqual(self.cli('--fail-on', 'MEDIUM')[0], 2)
                p.unlink()

    def test_docs_and_fences(self):
        for fence in ('```', '~~~', '   ````'):
            self.assertEqual(claims(fence + '\ninstrument recognition\n' + fence), (False, False))
        self.assertEqual(claims('`instrument recognition`'), (True, False))
        self.assertEqual(claims("doesn't recognize musical instruments"), (False, True))
        self.assertEqual(claims('INSTRUMENT-RECOGNITION'), (True, False))
        self.assertEqual(claims('xinstrument recognitionx'), (False, False))
        self.put('other.md', 'instrument recognition')
        self.assertEqual(self.cli()[0], 0)
        self.put('nested/docs/a.md', 'instrument recognition')
        self.assertEqual(self.cli()[0], 2)
        self.assertEqual(self.cli('--ignore', 'nested', '--ignore', 'other.md')[0], 0)

    def test_excluded_and_symlinks(self):
        self.put('README.md', 'instrument recognition')
        for name in ('fixtures/a.py', 'docs/a.py', 'examples/a.py'):
            self.put(name, 'e.detect_instrument(x)')
        outside = self.put('hidden/a.py', 'e.detect_instrument(x)')
        (self.root / 'link.py').symlink_to(outside)
        (self.root / 'linked').symlink_to(outside.parent, target_is_directory=True)
        self.assertFalse(audit(self.root, ['hidden'])['production_evidence'])
        self.assertEqual(self.cli('--ignore', 'hidden')[0], 2)

    def test_split_pair(self):
        self.put('a.py', 'm = InstrumentClassifier()')
        self.put('b.py', 'm.predict(x)')
        self.assertFalse(audit(self.root)['production_evidence'])

    def test_json_verbose_errors_version(self):
        self.put('README.md', 'instrument recognition')
        code, output = self.cli('--json')
        data = json.loads(output)
        self.assertEqual(code, 2)
        self.assertEqual(data['verdict'], 'FAIL')
        self.assertTrue(data['findings'][0]['message'])
        self.assertIn('inspected', self.cli('--verbose')[1])
        self.assertEqual(self.cli('--fail-on', 'LOW')[0], 2)
        self.put('README.md', 'ordinary prose')
        self.assertEqual(json.loads(self.cli('--json')[1])['verdict'], 'PASS')
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(SystemExit) as caught:
                main(['--version'])
        self.assertEqual(caught.exception.code, 0)
        self.assertEqual(output.getvalue().strip(), '0.1.0')
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main([str(self.root / 'missing')]), 1)
            for args in ([], ['--unknown'], [str(self.root), '--fail-on', 'BOGUS']):
                with self.assertRaises(SystemExit) as caught:
                    main(args)
                self.assertEqual(caught.exception.code, 1)

    def test_module_entry(self):
        result = subprocess.run([sys.executable, '-m', 'instrument_recognition_claim_audit', '--version'], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout.strip()), (0, '0.1.0'))

    def test_readme_self_audit(self):
        root = Path(__file__).resolve().parents[1]
        if (root / 'README.md').exists():
            self.assertEqual(claims((root / 'README.md').read_text()), (False, False))
            self.assertEqual(audit(root)['verdict'], 'PASS')


def add_case(name, source, expected):
    def check(self):
        self.assertEqual(evidence(source), expected, source)
    setattr(AuditTests, 'test_' + name, check)

for operation in sorted(GENERIC):
    add_case('attribute_' + operation, 'engine.' + operation + '(audio)', True)
    add_case('import_' + operation, 'from library import ' + operation + ' as op\nop(audio)', True)

POSITIVES = [
    'class classify_instrument: pass\ne.classify_instrument(x)',
    'from library import detect_instrument\ndetect_instrument(x)',
    'from library import InstrumentClassifier\nm = InstrumentClassifier(); m.predict(x)',
    'm = InstrumentClassifier(); m.predict(x)',
    'InstrumentClassifier().predict(x)',
    'm = MusicInstrumentClassifier(); m.predict(x)',
    'from library import InstrumentClassifier as IC\nm = IC(); m.predict(x)',
    'import library as lib\nm = lib.AudioInstrumentClassifier(); m.predict(x)',
    'lib.SongInstrumentClassifier().predict(x)',
    'def predict(x): pass\nm = InstrumentClassifier(); m.predict(x)',
    'm: object = InstrumentClassifier()\nm.predict(x)',
]
NEGATIVES = [
    'import instruments', 'librosa.load(x)', 'soundfile.read(x)', 'wave.open(x).readframes(2)', 'torchaudio.load(x)',
    'microphone.listen(x)', 'sounddevice.rec(x)', 'pyaudio.open().read(x)', 'audio.play(x)',
    'whisper.transcribe(x)', 'recognizer.recognize_google(x)', 'tts.speak(x)', 'vad.is_speech(x)',
    'silero.get_speech_timestamps(x)', 'pvporcupine.create(x)', 'm = Model(); m.predict(x)', 'e.detect_keyword(x)',
    'speechbrain.verify_files(a,b)', 'e.verify_speaker(x)', 'pipeline.diarize(x)', 'noisereduce.reduce_noise(x)',
    'df.enhance(x)', 'e.suppress_noise(x)', 'e.remove_noise(x)', 'acoustid.fingerprint_file(x)',
    'd = Dejavu(); d.recognize(x)', 'e.fingerprint_audio(x)', 'm = AudioTagging(); m.inference(x)',
    'YAMNet(x)', 'e.detect_sound_event(x)', 'demucs.separate(x)', 's = Separator(); s.separate(x)', 'e.separate_stems(x)',
    'librosa.beat.beat_track(x)', 'librosa.feature.tempo(x)', 'aubio.tempo(x)', 'RhythmExtractor()(x)',
    'librosa.piptrack(x)', 'librosa.yin(x)', 'crepe.predict(x)', 'aubio.pitch(x)', 'sound.to_pitch(x)',
    'librosa.onset.onset_detect(x)', 'e.detect_onsets(x)', 'librosa.onset.onset_strength(x)',
    'librosa.feature.chroma_cqt(x)', 'librosa.feature.chroma_cens(x)', 'librosa.feature.chroma_stft(x)',
    'librosa.feature.mfcc(x)', 'Chromagram()(x)', 'librosa.feature.zero_crossing_rate(x)',
    'ChordsDetection()(x)', 'ChordsDetectionBeats()(x)', 'e.detect_chords(x)', 'KeyExtractor()(x)', 'e.detect_key(x)',
    'basic_pitch.predict(x)', 'm = PianoTranscription(); m.transcribe(x)', 'e.transcribe_music(x)', 'e.audio_to_midi(x)', 'e.detect_notes(x)',
    'e.generate_audio(x)', 'e.synthesize(x)', 'e.classify_genre(x)', 'm = GenreClassifier(); m.predict(x)',
    'e.detect_mood(x)', 'e.recognize_emotion(x)', 'e.tag_audio(x)', 'model.predict(x)', 'model.forward(x)', 'e.classify(x)',
    'pipeline("audio-classification")(x)', 'm = PrettyMIDI(); i = Instrument(0); n = Note(1,2,3,4)',
    'music21.note.Note(x); music21.stream.Stream(x)', 'score.write("lilypond")', 'verovio.renderToSVG(x)',
    'hashlib.md5(data)', 'hashlib.sha256(data)', 'e.filter(x)', 'e.equalize(x)', 'e.mix(x)', 'e.normalize(x)',
    'e.detect_language(x)', 'e.translate(x)', 'from library import InstrumentClassifier', 'm = InstrumentClassifier()',
    'm = OtherClassifier(); m.predict(x)', 'class InstrumentClassifier:\n def predict(self,x): pass\nm = InstrumentClassifier(); m.predict(x)',
    'def InstrumentClassifier(): pass\nInstrumentClassifier().predict(x)',
    'def MusicInstrumentClassifier(): pass\nm = lib.MusicInstrumentClassifier(); m.predict(x)',
    'subprocess.run(["instrument-cli", "x"])', '"InstrumentClassifier().predict(x)"', 'e.detect_instrument',
    'def detect_instrument(x): pass\ne.detect_instrument(x)',
    'from lib import detect_instrument as op\ndef op(x): pass\nop(x)',
    'class E:\n def classify_instrument(self,x): pass\ne.classify_instrument(x)',
    'classify_instrument(x)', 'def broken(: e.classify_instrument(x)',
]
for i, source in enumerate(POSITIVES):
    add_case('pair_%03d' % i, source, True)
for i, source in enumerate(NEGATIVES):
    add_case('rejected_%03d' % i, source, False)

if __name__ == '__main__':
    unittest.main()
