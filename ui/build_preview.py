from pathlib import Path

def build_preview():
    tool=Path(__file__).resolve().parents[1]
    ui=tool/'ui'
    css=(ui/'style.css').read_text(encoding='utf-8-sig')
    data=(ui/'platform-data.js').read_text(encoding='utf-8-sig')
    loader=(ui/'data-loader.js').read_text(encoding='utf-8-sig')
    model=(ui/'frontend-model.js').read_text(encoding='utf-8-sig')
    js=(ui/'app.js').read_text(encoding='utf-8-sig')
    html='<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>板级工程配置</title><style>:root{color-scheme:light dark}body{margin:0;padding:20px;background:light-dark(#edf1f7,#121720)}#pbrd-ui{max-width:1400px;margin:auto}</style><style>'+css+'</style></head><body><div id="pbrd-ui"></div><script>'+data+'</script><script>'+loader+'</script><script>'+model+'</script><script>'+js+'</script></body></html>'
    (tool/'board-config-preview.html').write_text(html,encoding='utf-8')
    print('Built offline HTML:',len(html))

if __name__=='__main__':
    build_preview()
