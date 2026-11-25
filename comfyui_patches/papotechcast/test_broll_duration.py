import importlib,types,sys,unittest,tempfile,shutil,subprocess
from pathlib import Path
from unittest.mock import patch
pkg=types.ModuleType('papo_duration_test');pkg.__path__=[str(Path(__file__).parent)];sys.modules[pkg.__name__]=pkg
y=importlib.import_module('papo_duration_test.youtube_brolls')
class DurationTests(unittest.TestCase):
    def test_stream_duration_without_container_duration(self):
        with patch.object(y,'probe',return_value={'format':{},'streams':[{'codec_type':'video','duration':'4.25'}]}):
            self.assertEqual(y.video_duration('x'),4.25)
    def test_no_duration_is_not_replaced_with_requested_length(self):
        for info in ({'format':{},'streams':[{'codec_type':'video'}]}, {'format':{'duration':'nan'},'streams':[{'codec_type':'video'}]}, {'format':{'duration':'10'},'streams':[]}):
            with patch.object(y,'probe',return_value=info),self.assertRaises(ValueError):y.video_duration('x')
    def test_download_without_duration_is_converted_then_measured(self):
        fixture=Path('/mnt/build/projects/ComfyUI/input/papotechcast/exemplos/broll.mp4')
        original_run=y.subprocess.run
        original_probe=y.probe
        def dispatch(args,**kw):
            if args[:3]==[sys.executable,'-m','yt_dlp']:
                target=Path(args[args.index('-o')+1].replace('%(ext)s','mp4'));shutil.copy2(fixture,target)
                return subprocess.CompletedProcess(args,0,'','')
            return original_run(args,**kw)
        def probe(path):
            if Path(path).name=='trecho.mp4':
                return {'format':{},'streams':[{'codec_type':'video'}]}
            return original_probe(path)
        with tempfile.TemporaryDirectory() as root,patch.object(y.subprocess,'run',side_effect=dispatch),patch.object(y,'probe',side_effect=probe):
            _,duration=y.download_clip({'url':'https://www.youtube.com/watch?v=abcdefghijk','start':1,'end':2},720,root)
            self.assertAlmostEqual(duration,1,delta=.1)
    def test_empty_remote_section_retries_full_source_and_cuts_locally(self):
        fixture=Path('/mnt/build/projects/ComfyUI/input/papotechcast/exemplos/broll.mp4')
        original_run, original_probe = y.subprocess.run, y.probe
        downloads=[]
        def dispatch(args,**kw):
            if args[:3]==[sys.executable,'-m','yt_dlp']:
                downloads.append(args)
                target=Path(args[args.index('-o')+1].replace('%(ext)s','mp4'));shutil.copy2(fixture,target)
                return subprocess.CompletedProcess(args,0,'','')
            return original_run(args,**kw)
        def probe(path):
            return {'format':{},'streams':[]} if Path(path).name=='trecho.mp4' else original_probe(path)
        with tempfile.TemporaryDirectory() as root,patch.object(y.subprocess,'run',side_effect=dispatch),patch.object(y,'probe',side_effect=probe):
            relative,duration=y.download_clip({'url':'https://www.youtube.com/watch?v=abcdefghijk','start':1,'end':2},720,root)
            self.assertAlmostEqual(duration,1,delta=.1)
            self.assertEqual(len(downloads),2)
            self.assertNotIn('--download-sections',downloads[1])
            self.assertFalse(list((Path(root)/relative).parent.glob('download-*')))
if __name__=='__main__':unittest.main()
