import importlib.util,json,math,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

HERE=Path(__file__).parent
spec=importlib.util.spec_from_file_location('background_pipeline',HERE/'pipeline.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class BackgroundAudioTests(unittest.TestCase):
    def commands(self, run, volume=None, music='', srt='', with_audio=True, legacy=False):
        commands=[]
        def command(args):
            commands.append(args)
            if args[0]=='ffmpeg':Path(args[-1]).touch()
            return ''
        def probe(path):
            streams=[{'codec_type':'video'}]
            if with_audio or Path(path).name=='video_final.mp4':streams.append({'codec_type':'audio'})
            return {'format':{'duration':'1'},'streams':streams}
        assets={'background':'background.mp4','music':music,'brolls':[]}
        narration={'run':str(run),'audio':'voice.wav','duration':1.0}
        with patch.object(p,'command',side_effect=command),patch.object(p,'probe',side_effect=probe):
            if legacy:
                env={name:getattr(p,name) for name in ('math','json','Path','timeline')}
                env.update(command=command,probe=probe)
                exec((HERE/'fixtures/render_before_background.py').read_text(),env)
                env['render'](assets,narration,srt,'YouTube 720p',10,4,.08)
            elif volume is None:p.render(assets,narration,srt,'YouTube 720p',10,4,.08)
            else:p.render(assets,narration,srt,'YouTube 720p',10,4,.08,volume_fundo=volume)
        return commands

    def test_omitted_and_zero_keep_every_ffmpeg_argument_identical_to_previous_version(self):
        with tempfile.TemporaryDirectory() as folder:
            for music,srt in [('', ''),('music.wav',''),('music.wav','legendas.srt'),('','legendas.srt')]:
                with self.subTest(music=music,srt=srt):
                    run=Path(folder)
                    old=self.commands(run,music=music,srt=srt,legacy=True)
                    self.assertEqual(old,self.commands(run,music=music,srt=srt))
                    self.assertEqual(old,self.commands(run,volume=0.0,music=music,srt=srt))

    def test_background_audio_loops_independently_and_keeps_voice_loudnorm(self):
        with tempfile.TemporaryDirectory() as folder:
            args=self.commands(Path(folder),volume=.25)[-1]
        self.assertIn(['-stream_loop','-1','-i','background.mp4'],[args[i:i+4] for i in range(len(args))])
        graph=args[args.index('-filter_complex')+1]
        self.assertIn('[1:a]loudnorm=I=-16:TP=-1.5:LRA=11,asetpts=PTS-STARTPTS[voice]',graph)
        self.assertIn('[2:a:0]asetpts=PTS-STARTPTS,volume=0.25,atrim=duration=1.0[background]',graph)
        self.assertIn('[voice][background]amix=inputs=2:duration=first:normalize=0[a]',graph)

    def test_music_and_background_use_three_way_mix(self):
        with tempfile.TemporaryDirectory() as folder:args=self.commands(Path(folder),volume=1.5,music='music.wav')[-1]
        graph=args[args.index('-filter_complex')+1]
        self.assertIn('[2:a]volume=0.08[music]',graph)
        self.assertIn('[3:a:0]asetpts=PTS-STARTPTS,volume=1.5',graph)
        self.assertIn('amix=inputs=3:duration=first:normalize=0[a]',graph)

    def test_silent_background_warns_and_keeps_the_previous_command(self):
        with tempfile.TemporaryDirectory() as folder:
            run=Path(folder)
            old=self.commands(run,legacy=True,with_audio=False)
            with self.assertLogs('papotechcast',level='WARNING') as logs:
                new=self.commands(run,volume=.5,with_audio=False)
            self.assertEqual(old,new)
            self.assertIn('não possui faixa de áudio',' '.join(logs.output))

    def test_invalid_volume_is_rejected_before_rendering(self):
        for value in (-.01,1.51,float('nan'),float('inf'),float('-inf'),None,'bad'):
            with self.subTest(value=value),patch.object(p,'command') as command,self.assertRaisesRegex(ValueError,'volume_fundo'):
                p.render({}, {}, '', 'YouTube 720p',10,4,.08,volume_fundo=value)
            command.assert_not_called()

if __name__=='__main__':unittest.main()
