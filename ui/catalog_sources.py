"""Read-only catalog extraction. Runtime uses Python standard library only."""
from pathlib import Path
import re, hashlib

MODULE_NAMES={'Analog':'analog','Axis':'axis','IcCard':'ic_card','ExtRtc':'ext_rtc','MiscCtrl':'misc_ctrl','PwrCtrl':'pwr_ctrl','ExtInt':'ext_int','CanTrx':'can_trx','BatChg':'bat_chg','BatChgMgr':'bat_chg_mgr','XcuSpi':'xcu_spi','SecurityBoot':'security_boot'}

def read_enums(path):
    raw=Path(path).read_bytes()
    text=raw.decode('utf-8-sig')
    catalog=[]
    for match in re.finditer(r'\b(kBrd(\w+?)Base(?:Id)?(\w+))\s*=\s*[^\n]+?///<\s*([^\r\n]+)',text):
        base,kind,suffix,label=match.groups()
        catalog.append({'module':MODULE_NAMES.get(kind,kind.lower()),'name':label.strip(),'base_enum':base,'enum':'kBrd_'+kind+'Id'+suffix})
    if not catalog:
        raise ValueError('No annotated board enums found in UTF-8 header')
    return {'enum_catalog':catalog,'source_hash':hashlib.sha256(raw).hexdigest(),'source':str(path)}
