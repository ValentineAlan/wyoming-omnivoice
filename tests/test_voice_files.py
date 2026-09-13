import tempfile, unittest
from pathlib import Path
from voice_files import discover_voices, resolve_voice, seed_example


class VoiceFilesTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def pair(self, name, text='The exact reference transcript.'):
        (self.root / (name+'.wav')).write_bytes(b'RIFF')
        (self.root / (name+'.txt')).write_text(text, encoding='utf-8')

    def test_names_and_transcript(self):
        self.pair('david_reference', '\ufeff  David speaks.\n')
        self.pair('jess_reference')
        self.assertEqual(list(discover_voices(self.root)), ['david', 'jess'])
        wav, text = resolve_voice(self.root, 'david')
        self.assertEqual(Path(wav).name, 'david_reference.wav')
        self.assertEqual(text, 'David speaks.')

    def test_plain_wav_name(self):
        self.pair('alex')
        self.assertEqual(Path(resolve_voice(self.root, 'alex')[0]).name, 'alex.wav')

    def test_missing_transcript(self):
        (self.root/'david_reference.wav').touch()
        with self.assertRaisesRegex(ValueError, 'paired file'):
            resolve_voice(self.root, 'david')

    def test_empty_transcript(self):
        self.pair('david_reference', ' \n')
        with self.assertRaisesRegex(ValueError, 'empty'):
            resolve_voice(self.root, 'david')

    def test_duplicate_names(self):
        self.pair('david_reference')
        self.pair('david')
        with self.assertRaisesRegex(ValueError, 'Ambiguous'):
            discover_voices(self.root)

    def test_path_instead_of_name_is_rejected(self):
        self.pair('david_reference')
        with self.assertRaisesRegex(ValueError, 'Unknown voice'):
            resolve_voice(self.root, '../david')

    def test_first_start_and_preserve_existing(self):
        self.pair('example_reference')
        dest = self.root / 'mounted'
        self.assertTrue(seed_example(dest, self.root))
        self.assertEqual(resolve_voice(dest, 'example')[1], 'The exact reference transcript.')
        (dest/'example_reference.txt').write_text('User changed this.')
        self.assertFalse(seed_example(dest, self.root))
        self.assertEqual(resolve_voice(dest, 'example')[1], 'User changed this.')

    def test_partial_existing_pair_is_not_overwritten(self):
        self.pair('example_reference')
        dest = self.root / 'mounted'
        dest.mkdir()
        (dest/'example_reference.wav').write_bytes(b'personal recording')
        self.assertFalse(seed_example(dest, self.root))
        self.assertFalse((dest/'example_reference.txt').exists())


if __name__ == '__main__':
    unittest.main()
