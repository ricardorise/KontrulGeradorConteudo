import importlib.util,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('overlap_pipeline',Path(__file__).with_name('pipeline.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
class OverlapTests(unittest.TestCase):
    def test_reported_case_keeps_phrase_times_and_shortens_only_previous_broll(self):
        assets={'background':'bg','brolls':[dict(source='a',at=3.333,duration=44,phrase='frase A'),dict(source='b',at=7.345,duration=3,phrase='frase B'),dict(source='c',at=30.104,duration=36,phrase='frase C')]}
        events=p.timeline(assets,90,10,4)
        clips=[e for e in events if e['kind']=='broll']
        self.assertEqual([e['start'] for e in clips],[3.333,7.345,30.104])
        self.assertAlmostEqual(clips[0]['duration'],4.012)
        self.assertEqual(clips[0]['requested_duration'],44)
        self.assertEqual(clips[0]['trim_reason'],'next_broll_start')
        for left,right in zip(events,events[1:]):self.assertAlmostEqual(left['start']+left['duration'],right['start'])
        self.assertAlmostEqual(sum(e['duration'] for e in events),90)
        self.assertEqual(assets['brolls'][0]['duration'],44)
    def test_same_time_is_not_silently_hidden(self):
        assets={'background':'bg','brolls':[dict(source='a',at=3,duration=4,phrase='A'),dict(source='b',at=3,duration=4,phrase='B')]}
        with self.assertRaisesRegex(ValueError,'simultânea'):p.timeline(assets,10,1,4)
    def test_manual_overlap_still_requires_explicit_correction(self):
        assets={'background':'bg','brolls':[dict(source='a',at=1,duration=5),dict(source='b',at=2,duration=2)]}
        with self.assertRaisesRegex(ValueError,'sobrepõe'):p.timeline(assets,10,1,4)
if __name__=='__main__':unittest.main()
