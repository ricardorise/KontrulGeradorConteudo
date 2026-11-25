import { app } from '../../scripts/app.js';
import { api } from '../../scripts/api.js';

app.registerExtension({
    name: 'PapoTechCast.Files',
    async nodeCreated(node) {
        if (node.comfyClass === 'PapoNarration') {
            const dialog = (title) => {
                const modal = document.createElement('dialog');
                modal.style.cssText = 'background:#242424;color:#eee;padding:24px;border:1px solid #666;border-radius:10px;width:620px;max-width:90vw;max-height:80vh';
                const heading = document.createElement('h3'); heading.textContent=title; modal.append(heading);
                const close = document.createElement('button'); close.textContent='Fechar'; close.style.marginTop='16px'; close.onclick=()=>modal.close();
                modal.addEventListener('close',()=>modal.remove());
                document.body.append(modal); modal.showModal();
                return {modal,close};
            };
            node.addWidget('button','Configuração ElevenLabs',null,async()=>{
                const {modal,close}=dialog('Configurar ElevenLabs');
                const response=await api.fetchApi('/papotechcast/elevenlabs/status');
                const state=await response.json();
                const status=document.createElement('p');
                status.textContent=state.configured ? 'Chave configurada. Voz padrão: '+(state.default_voice||'não definida') : 'Falta configurar a chave e a voz padrão no servidor.';
                const help=document.createElement('p'); help.textContent='Execute o comando abaixo no terminal deste computador. A chave será pedida com entrada oculta, ficará somente no servidor e não será salva no workflow. A configuração consulta as vozes, sem gerar áudio.';
                const code=document.createElement('pre');code.style.cssText='white-space:pre-wrap;overflow-wrap:anywhere;background:#111;padding:12px;user-select:text';
                code.textContent='ssh -t -F /dev/null rises@rises /mnt/build/envs/comfyui/bin/python /mnt/build/projects/ComfyUI/custom_nodes/papotechcast/configure_elevenlabs.py';
                const note=document.createElement('p');note.textContent='Depois escolha ElevenLabs em provedor. Os campos voz_salva, descricao_voz e referencia são usados apenas pelo VoiceStudio. A ElevenLabs utiliza voz_elevenlabs e seus controles próprios.';
                modal.append(status,help,code,note,close);
            },{serialize:false});
            node.addWidget('button','Vozes ElevenLabs',null,async()=>{
                const {modal,close}=dialog('Escolher voz ElevenLabs');
                const status=document.createElement('p');status.textContent='Consultando vozes da conta…';modal.append(status);
                try {
                    const response=await api.fetchApi('/papotechcast/elevenlabs/voices',{timeoutMs:60000});
                    const data=await response.json();
                    if(!response.ok)throw new Error(data.error||'Não foi possível consultar as vozes.');
                    status.textContent='Selecione uma voz. Esta ação não gera áudio.';
                    for(const voice of data.voices){
                        const button=document.createElement('button');button.textContent=voice.name+' ('+voice.category+')';button.style.cssText='display:block;padding:9px;margin:6px 0;width:100%;text-align:left';
                        button.onclick=()=>{
                            node.widgets.find(w=>w.name==='voz_elevenlabs').value=voice.voice_id;
                            node.widgets.find(w=>w.name==='provedor').value='ElevenLabs';
                            app.graph.setDirtyCanvas(true,true);modal.close();
                        };
                        modal.append(button);
                    }
                }catch(error){status.textContent=error.message;}
                modal.append(close);
            },{serialize:false});
            return;
        }
        if (node.comfyClass !== 'PapoAssets') return;
        const upload = (name, label, accept, multiple = false) => {
            node.addWidget('button', label, null, async () => {
                const picker = document.createElement('input');
                picker.type = 'file'; picker.accept = accept; picker.multiple = multiple;
                picker.onchange = async () => {
                    const widget = node.widgets.find(w => w.name === name);
                    const paths = [];
                    try {
                        for (const file of picker.files) {
                            const data = new FormData();
                            data.append('image', file);
                            data.append('type', 'input');
                            data.append('subfolder', 'papotechcast');
                            const response = await api.fetchApi('/upload/image', { method: 'POST', body: data, timeoutMs: 600000, skipStatusRetry: true });
                            if (!response.ok) throw new Error(`Falha no upload: ${response.status}`);
                            const result = await response.json();
                            paths.push([result.subfolder, result.name].filter(Boolean).join('/'));
                        }
                        widget.value = multiple ? [widget.value, ...paths].filter(Boolean).join('\n') : paths[0];
                        app.graph.setDirtyCanvas(true, true);
                    } catch (error) { alert(error.message); }
                };
                picker.click();
            }, {serialize: false});
        };
        node.addWidget('button', 'Vincular B-roll a frase do roteiro', null, () => {
            const catalog = node.widgets.find(w => w.name === 'brolls');
            const resources = String(catalog?.value || '').split('\n').map(v => v.trim()).filter(v => v && !v.startsWith('#'));
            if (!resources.length) return alert('Cadastre ou envie um B-roll primeiro.');
            const selection = prompt('Escolha o número do B-roll:\n' + resources.map((v,i) => `${i+1}. ${v}`).join('\n'));
            if (selection === null) return;
            const resource = resources[Number(selection)-1];
            if (!resource) return alert('Recurso inválido.');
            const phrase = prompt('Cole uma frase única, idêntica ao roteiro. O B-roll entrará na primeira palavra da frase:');
            if (!phrase?.trim()) return;
            if (/[|\n]/.test(phrase)) return alert('Use uma frase em uma linha, sem o caractere |.');
            let target = node;
            const visited = new Set();
            while (target && !visited.has(target.id)) {
                visited.add(target.id);
                const value = target.type === 'PrimitiveStringMultiline' && target.widgets?.find(w => w.name === 'value');
                if (value) {
                    const lines = String(value.value || '').split('\n').filter(line => line.trim() && line.split('|')[0].trim() !== resource && line.split('|')[0].trim() !== resource.split('/').pop());
                    lines.push(`${resource} | frase:${phrase.trim()}`);
                    value.value = lines.join('\n');
                    app.graph.setDirtyCanvas(true, true);
                    alert('Frase vinculada. O tempo será calculado pelo WhisperX local durante o Run. Salve o fluxo para manter a alteração.');
                    return;
                }
                const input = target.inputs?.find(i => ['brolls_timeline','brolls_locais'].includes(i.name));
                const link = input?.link != null && (app.graph.links.get?.(input.link) ?? app.graph.links[input.link]);
                target = link && app.graph.getNodeById(link.origin_id);
            }
            alert('Conecte uma lista de edição à entrada brolls_timeline. Formato: caminho | frase:trecho do roteiro');
        }, {serialize: false});
        node.addWidget('button', 'Adicionar B-roll por URL', null, () => {
            const modal = document.createElement('dialog');
            modal.style.cssText = 'background:#242424;color:#eee;border:1px solid #666;border-radius:12px;padding:24px;width:460px;max-width:90vw';
            const heading = document.createElement('h3');
            heading.textContent = 'Cadastrar B-roll do YouTube';
            const help = document.createElement('p');
            help.textContent = 'Cadastre a URL e o intervalo. O download e o recorte só acontecerão no Run. Use a URL cadastrada como referência na lista de edição.';
            help.style.cssText = 'font-size:13px;line-height:1.5;color:#bbb';
            const field = (label, value, placeholder) => {
                const wrapper = document.createElement('label');
                wrapper.textContent = label;
                wrapper.style.cssText = 'display:block;margin:12px 0';
                const input = document.createElement('input');
                input.value = value; input.placeholder = placeholder;
                input.style.cssText = 'display:block;width:100%;box-sizing:border-box;background:#111;color:#fff;border:1px solid #666;padding:9px;margin-top:5px';
                wrapper.append(input); modal.append(wrapper); return input;
            };
            modal.append(heading, help);
            const url = field('URL do vídeo', '', 'https://www.youtube.com/watch?v=...');
            const start = field('Início do trecho na fonte', '', '05:26');
            const end = field('Fim do trecho na fonte', '', '05:50');
            const status = document.createElement('p');
            status.style.cssText = 'font-size:13px;overflow-wrap:anywhere';
            const download = document.createElement('button');
            download.textContent = 'Adicionar à lista (sem baixar)';
            download.style.cssText = 'padding:10px;margin:16px 8px 0 0;background:#2788c7;color:white;border:0;border-radius:5px';
            const close = document.createElement('button');
            close.textContent = 'Fechar'; close.style.cssText = 'padding:10px';
            close.onclick = () => modal.close();
            modal.addEventListener('close', () => modal.remove());
            download.onclick = () => {
                try {
                    const parseTime = value => {
                        const text = value.trim().replace(',', '.');
                        if (!/^\d+(?::\d{1,2}){0,2}(?:\.\d+)?$/.test(text)) throw new Error('Use segundos ou MM:SS nos intervalos.');
                        const parts = text.split(':').map(Number);
                        if (parts.slice(1).some(v => v >= 60)) throw new Error('Minutos e segundos devem ser menores que 60.');
                        const total = parts.reduce((sum, value) => sum * 60 + value, 0);
                        if (!Number.isFinite(total)) throw new Error('Tempo inválido.');
                        return total;
                    };
                    const link = new URL(url.value.trim());
                    if (link.protocol !== 'https:' || !['youtube.com','www.youtube.com','m.youtube.com','youtu.be'].includes(link.hostname) || link.username || link.password) throw new Error('Informe um link HTTPS do YouTube.');
                    const begin = parseTime(start.value), finish = parseTime(end.value);
                    if (finish <= begin) throw new Error('O fim deve ser maior que o início.');
                    link.hash = 't=' + begin + ',' + finish;
                    const widget = node.widgets.find(w => w.name === 'brolls');
                    const paths = String(widget.value || '').split('\n').map(v => v.trim()).filter(Boolean);
                    widget.value = [...new Set([...paths, link.toString()])].join('\n');
                    app.graph.setDirtyCanvas(true, true);
                    status.textContent = 'Cadastrado: ' + link.toString() + '. Será baixado e recortado somente no Run.';
                } catch (error) { status.textContent = error.message; }
            };
            modal.append(status, download, close);
            document.body.append(modal); modal.showModal();
        }, {serialize: false});
        node.addWidget('button', 'Gerenciar / remover B-rolls', null, () => {
            const modal = document.createElement('dialog');
            modal.style.cssText = 'background:#242424;color:#eee;border:1px solid #666;border-radius:12px;padding:24px;width:760px;max-width:90vw;max-height:80vh';
            const heading = document.createElement('h3'); heading.textContent = 'Gerenciar B-rolls';
            const help = document.createElement('p'); help.textContent = 'Remova o recurso da lista ou exclua também os arquivos do servidor. As referências deste recurso na lista de edição serão removidas.';
            const list = document.createElement('div');
            const status = document.createElement('p'); status.style.overflowWrap = 'anywhere';
            const close = document.createElement('button'); close.textContent = 'Fechar'; close.onclick = () => modal.close();
            modal.addEventListener('close', () => modal.remove());
            const widget = node.widgets.find(w => w.name === 'brolls');
            const referenceKey = value => {
                const raw = value.split('|')[0].trim();
                if (!raw.startsWith('https://')) return raw;
                try {
                    const url = new URL(raw);
                    const id = url.hostname === 'youtu.be' ? url.pathname.slice(1) : url.searchParams.get('v') || url.pathname.split('/').filter(Boolean).at(-1);
                    return 'youtube:' + id + url.hash;
                } catch { return raw; }
            };
            const removeFromLists = resource => {
                const current = String(widget.value || '').split('\n');
                const key = referenceKey(resource);
                const keys = new Set([key]);
                if (key.startsWith('youtube:')) {
                    const base = key.split('#')[0];
                    if (!current.some(line => line !== resource && referenceKey(line).split('#')[0] === base)) keys.add(base);
                } else {
                    const name = key.split('/').at(-1);
                    if (!current.some(line => line !== resource && referenceKey(line).split('/').at(-1) === name)) keys.add(name);
                }
                app.graph.beforeChange?.();
                widget.value = current.filter(line => line.trim() !== resource).join('\n');
                const visited = new Set();
                const visit = upstream => {
                    if (!upstream || visited.has(upstream.id)) return;
                    visited.add(upstream.id);
                    const kind = upstream.comfyClass || upstream.type;
                    const names = kind === 'PrimitiveStringMultiline' ? ['value'] : kind === 'PapoYouTubeBrolls' ? ['lista_youtube'] : [];
                    for (const name of names) {
                        const field = upstream.widgets?.find(w => w.name === name);
                        if (field) field.value = String(field.value || '').split('\n').filter(line => !keys.has(referenceKey(line))).join('\n');
                    }
                    for (const input of upstream.inputs || []) {
                        if (input.name !== 'brolls_locais' || input.link == null) continue;
                        const link = (app.graph.links.get?.(input.link) ?? app.graph.links[input.link]);
                        if (link) visit(app.graph.getNodeById(link.origin_id));
                    }
                };
                const input = node.inputs?.find(i => i.name === 'brolls_timeline');
                const link = input?.link != null ? (app.graph.links.get?.(input.link) ?? app.graph.links[input.link]) : null;
                if (link) visit(app.graph.getNodeById(link.origin_id));
                app.graph.afterChange?.();
                app.graph.setDirtyCanvas(true, true);
                render();
            };
            const render = () => {
                list.replaceChildren();
                const resources = String(widget.value || '').split('\n').map(v => v.trim()).filter(Boolean);
                if (!resources.length) { list.textContent = 'Nenhum B-roll cadastrado.'; return; }
                for (const resource of resources) {
                    const row = document.createElement('div');
                    row.style.cssText = 'border-top:1px solid #555;padding:14px 0';
                    const label = document.createElement('div'); label.textContent = resource;
                    label.style.cssText = 'overflow-wrap:anywhere;margin-bottom:10px;font-size:13px';
                    const remove = document.createElement('button'); remove.textContent = 'Remover da lista';
                    remove.style.cssText = 'padding:8px;margin-right:8px';
                    remove.onclick = () => { removeFromLists(resource); status.textContent = 'Recurso removido da lista; arquivos mantidos no servidor.'; };
                    const erase = document.createElement('button'); erase.textContent = 'Excluir arquivo do servidor';
                    erase.style.cssText = 'padding:8px;background:#843c3c;color:#fff;border:0';
                    erase.onclick = async () => {
                        erase.disabled = true;
                        try {
                            const preview = await api.fetchApi('/papotechcast/resources/delete-preview', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({resource}),skipStatusRetry:true});
                            const details = await preview.json();
                            if (!preview.ok) throw new Error(details.error || 'Não foi possível consultar o recurso.');
                            if (!details.files.length) {
                                status.textContent = 'Esse recurso não tem arquivo salvo no servidor. Use Remover da lista.'; return;
                            }
                            const names = details.files.map(f => f.path).join('\n');
                            if (!confirm('Excluir permanentemente estes arquivos do servidor?\n\n' + names + '\n\nO recurso também será removido desta lista e da edição.')) return;
                            const response = await api.fetchApi('/papotechcast/resources/delete', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({resource,expected:details.files,confirm:true}),skipStatusRetry:true});
                            const result = await response.json();
                            if (!response.ok) throw new Error(result.error || 'Não foi possível excluir.');
                            removeFromLists(resource);
                            status.textContent = 'Arquivos excluídos do servidor e recurso removido da lista.';
                        } catch (error) { status.textContent = error.message; }
                        finally { erase.disabled = false; }
                    };
                    row.append(label, remove, erase); list.append(row);
                }
            };
            modal.append(heading, help, list, status, close);
            document.body.append(modal); render(); modal.showModal();
        }, {serialize:false});
        upload('brolls', 'Enviar B-rolls do computador', 'video/*', true);
        upload('background', 'Enviar background', 'video/*');
        upload('trilha', 'Enviar trilha (opcional)', 'audio/*');
        upload('referencia_voz', 'Enviar voz de referência (opcional)', 'audio/*');
    },
    async beforeRegisterNodeDef(nodeType, nodeData) {
        const widgetNames = {
            PapoAssets: ['background','brolls','trilha','referencia_voz'],
            PapoNarration: ['voz_salva','descricao_voz','transcricao_referencia','idioma','seed','control_after_generate','provedor','voz_elevenlabs','modelo_elevenlabs','estabilidade_elevenlabs','similaridade_elevenlabs','velocidade_elevenlabs','estilo_elevenlabs','idioma_elevenlabs'],
            PapoCaptions: ['ativar'],
            PapoRender: ['formato','intervalo_broll','duracao_broll','volume_trilha','volume_fundo'],
            PapoYouTube: ['titulo','descricao','tags','privacidade','conteudo_infantil','midia_sintetica','acao'],
            PapoYouTubeBrolls: ['lista_youtube','resolucao']
        };
        if (widgetNames[nodeData.name]) {
            nodeData.fallbackWidgetsValuesNames = widgetNames[nodeData.name];
            if (nodeType.nodeData) nodeType.nodeData.fallbackWidgetsValuesNames = widgetNames[nodeData.name];
        }
        if (nodeData.name !== 'PapoYouTube') return;
        const original = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            original?.apply(this, arguments);
            this.papoPreview?.onRemove?.();
            if (this.papoPreview) this.removeWidget(this.widgets.indexOf(this.papoPreview));
            const file = message.papo_video?.[0];
            if (!file) return;
            const wrapper = document.createElement('div');
            const url = api.apiURL('/view?' + new URLSearchParams({filename: file.filename, subfolder: file.subfolder, type: file.type}));
            const player = document.createElement('video');
            player.controls = true; player.src = url; player.style.width = '100%'; player.style.maxHeight = '230px';
            const link = document.createElement('a');
            link.href = url; link.download = file.filename; link.textContent = 'Baixar vídeo final';
            link.style.display = 'block'; link.style.color = '#7fcfff';
            const report = JSON.parse(message.text?.[0] || '{}');
            const status = document.createElement('p');
            status.textContent = report.status || '';
            status.style.color = '#ddd';
            wrapper.append(status, player, link);
            if (report.url?.startsWith('https://www.youtube.com/watch?v=')) {
                const youtube = document.createElement('a');
                youtube.href = report.url; youtube.textContent = 'Abrir vídeo no YouTube';
                youtube.target = '_blank'; youtube.rel = 'noopener';
                youtube.style.display = 'block'; wrapper.append(youtube);
            }
            this.papoPreview = this.addDOMWidget('papo_preview', 'preview', wrapper, { serialize: false, hideOnZoom: false });
            this.papoPreview.computeSize = () => [400, 260];
            this.setSize([Math.max(440, this.size[0]), Math.max(650, this.size[1])]);
        };
    }
});
