"""CPU-only synthetic smoke test; no TTS, WhisperX, external API, or GPU."""
import importlib.util,json,re,tempfile,hashlib
from pathlib import Path
HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('smoke_pipeline',HERE/'pipeline.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
root=Path(tempfile.mkdtemp(prefix='papotech-background-smoke-'))
def ff(args):return p.command(['ffmpeg','-y','-hide_banner','-loglevel','error']+list(map(str,args)))
bg=root/'background.mp4';silent=root/'background-silent.mp4';broll=root/'broll.mp4';voice=root/'voice.wav';music=root/'music.wav'
ff(['-f','lavfi','-i','color=c=blue:s=320x180:r=30:d=1','-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=1','-c:v','libx264','-threads','2','-c:a','aac','-shortest',bg])
ff(['-i',bg,'-an','-c:v','copy',silent])
ff(['-f','lavfi','-i','color=c=red:s=320x180:r=30:d=2','-f','lavfi','-i','sine=frequency=1800:sample_rate=48000:duration=2','-c:v','libx264','-threads','2','-c:a','aac','-shortest',broll])
ff(['-f','lavfi','-i','anullsrc=r=48000:cl=mono','-t','3.2','-c:a','pcm_s16le',voice])
ff(['-f','lavfi','-i','sine=frequency=880:sample_rate=48000:duration=1','-c:a','pcm_s16le',music])
def measure(file,start=0,length=3.2,extra=''):
    import subprocess
    filters=f'atrim=start={start}:duration={length},asetpts=PTS-STARTPTS,'+(extra+',' if extra else '')+'volumedetect'
    result=subprocess.run(['ffmpeg','-hide_banner','-i',str(file),'-vn','-af',filters,'-f','null','-'],capture_output=True,text=True,check=True)
    return float(re.search(r'mean_volume: (-?[\d.]+) dB',result.stderr).group(1))
results={};outputs={}
for label,volume,background,trilha in [('zero',0,bg,''),('background',.5,bg,''),('silent_background',.5,silent,''),('music_and_background',.5,bg,str(music))]:
    run=root/label;run.mkdir()
    assets={'background':str(background),'music':trilha,'brolls':[{'source':str(broll),'at':.6,'duration':2}]}
    narration={'audio':str(voice),'run':str(run),'duration':3.2}
    video=p.render(assets,narration,'','YouTube 720p',10,4,.08,volume_fundo=volume)
    results[label]={'mean_db':measure(video),'middle_db':measure(video,1.2,.4),'tail_db':measure(video,2.8,.3),'duration':float(p.probe(video)['format']['duration'])}
    outputs[label]=video
assert results['zero']['mean_db'] < -80
assert results['silent_background']['mean_db'] < -80
assert results['background']['mean_db'] > results['zero']['mean_db']+20
assert results['background']['middle_db'] > -40  # continues during B-roll
assert results['background']['tail_db'] > -40    # continues after looping the 1s source
assert all(abs(r['duration']-3.2)<.1 for r in results.values())
# B-roll's own 1800 Hz tone must remain discarded.
results['broll_1800hz_db']=measure(outputs['background'],1.2,.4,'bandpass=f=1800:width_type=h:width=50')
assert results['broll_1800hz_db'] < -50
(root/'smoke-results.json').write_text(json.dumps(results,indent=2))
print(json.dumps({'directory':str(root),'results':results},indent=2))
