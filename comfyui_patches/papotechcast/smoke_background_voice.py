"""Audible voice + background, CPU only; verify each frequency remains in the mix."""
import importlib.util,json,re,subprocess
from pathlib import Path
spec=importlib.util.spec_from_file_location('voice_mix_pipeline',Path(__file__).with_name('pipeline.py'));p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
root=max(Path('/tmp').glob('papotech-background-smoke-*'),key=lambda d:d.stat().st_mtime)
voice=root/'voice-tone.wav'
p.command(['ffmpeg','-y','-v','error','-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=3.2','-c:a','pcm_s16le',str(voice)])
def level(file,frequency=None):
    graph=(f'bandpass=f={frequency}:width_type=h:width=50,' if frequency else '')+'volumedetect'
    r=subprocess.run(['ffmpeg','-hide_banner','-i',str(file),'-vn','-af',graph,'-f','null','-'],capture_output=True,text=True,check=True)
    return float(re.search(r'mean_volume: (-?[\d.]+) dB',r.stderr).group(1))
results={}
for label,volume in [('voice_zero',0),('voice_background',.5)]:
    run=root/label;run.mkdir()
    assets={'background':str(root/'background.mp4'),'music':'','brolls':[{'source':str(root/'broll.mp4'),'at':.6,'duration':2}]}
    video=p.render(assets,{'audio':str(voice),'run':str(run),'duration':3.2},'','YouTube 720p',10,4,.08,volume_fundo=volume)
    results[label]={'mean_db':level(video),'background_440hz_db':level(video,440),'voice_880hz_db':level(video,880)}
assert results['voice_background']['background_440hz_db'] > results['voice_zero']['background_440hz_db']+10
assert abs(results['voice_background']['voice_880hz_db']-results['voice_zero']['voice_880hz_db'])<1
(root/'voice-mix-results.json').write_text(json.dumps(results,indent=2))
print(json.dumps({'directory':str(root),'results':results},indent=2))
