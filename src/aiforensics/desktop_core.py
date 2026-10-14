"""Offline desktop project store and allowlisted bridge to the tested physics CLI.

The desktop is *not* an AI-origin detector. Uploaded images have unverified
provenance; other physics modules require their documented calibration/measurement
JSON contracts. No shell evaluation or network communication.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

from .evidence_contract import MODULES

COMMANDS = {
 "P1-G01":"analyze", "P1-G02":"calibrate-segments",
 "P1-G03":"analyze-g03", "P1-G04":"validate-g04",
 "P2-S01":"analyze-shadows", "P2-S02":"analyze-multilight",
 "P2-S03":"analyze-light-3d", "P2-S04":"analyze-solar",
 "P2-S05":"analyze-penumbra",
 "P3-R01":"analyze-mirror", "P3-R02":"analyze-refraction",
 "P3-R03":"analyze-mirror-chain",
 "P4-O01":"analyze-lens", "P4-O02":"analyze-defocus",
 "P4-O03":"analyze-optics", "P4-O04":"analyze-vignetting",
 "P5-D01":"analyze-depth-contact", "P5-D02":"analyze-occlusion",
 "P5-D03":"analyze-static",
 "P6-M01":"analyze-material", "P6-M02":"analyze-microfacet",
 "P6-M03":"analyze-combined-material",
 "P7-S01":"analyze-sensor-noise", "P7-S02":"analyze-sensor-fingerprint",
 "P8-E01":"analyze-evidence", "P8-E02":"analyze-fusion",
 "P8-E03":"explain-evidence",
}
IMAGE_ONLY = frozenset({"P1-G01"})
IMAGE_EXTENSIONS = frozenset({".png",".jpg",".jpeg",".tif",".tiff",".bmp"})
SCHEMA = "fakeproof.desktop.project.v1"


class DesktopIntegrationError(ValueError):
    pass


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for block in iter(lambda: source.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def safe_project_name(name):
    if not isinstance(name,str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",name):
        raise DesktopIntegrationError("Proje adı yalnız ASCII harf, rakam, - ve _ içermelidir")
    return name


def module_catalog():
    result=[{"id":k,"name":v,"command":COMMANDS[k],
             "input":"image" if k in IMAGE_ONLY else "json"} for k,v in MODULES.items()]
    result += [{"id":key,"name":label,"command":COMMANDS[key],"input":"json"}
               for key,label in (("P8-E01","Tekil fiziksel kanıt"),
                                 ("P8-E02","Bağımlı hipotezler"),
                                 ("P8-E03","Açıklanabilir JSON/HTML rapor"))]
    return result


def atomic_json(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp = tempfile.mkstemp(dir=path.parent,prefix=".project-",suffix=".tmp")
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as output:
            json.dump(content,output,indent=2,ensure_ascii=False,allow_nan=False)
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Project:
    def __init__(self,workspace,name):
        self.name=safe_project_name(name)
        self.root=Path(workspace).expanduser().resolve()/self.name
        for part in ("images","manifests","runs","exports"):
            (self.root/part).mkdir(parents=True,exist_ok=True)
        self.file=self.root/"project.json"
        if self.file.exists():
            self.data=json.loads(self.file.read_text(encoding="utf-8"))
            if (self.data.get("schema_version")!=SCHEMA or
                    self.data.get("name")!=name or
                    not isinstance(self.data.get("images"),list) or
                    not isinstance(self.data.get("runs"),list)):
                raise DesktopIntegrationError("Geçersiz proje kayıt sözleşmesi")
        else:
            self.data={"schema_version":SCHEMA,"name":name,
                       "data_scope":"local_unverified_or_synthetic",
                       "images":[],"runs":[],"calibration":None}
            self.save()

    def save(self):
        atomic_json(self.file,self.data)

    def import_image(self,path):
        source=Path(path).expanduser().resolve(strict=True)
        if (not source.is_file() or source.suffix.lower() not in IMAGE_EXTENSIONS
                or not 0<source.stat().st_size<=200*1024*1024):
            raise DesktopIntegrationError("Desteklenmeyen görüntü türü veya boyut")
        digest=sha256(source)
        for item in self.data["images"]:
            if item["sha256"]==digest:
                return item
        filename=digest[:16]+"_"+re.sub(r"[^a-zA-Z0-9._-]","_",source.name)[:110]
        target=self.root/"images"/filename
        shutil.copyfile(source,target)
        if sha256(target)!=digest:
            target.unlink(missing_ok=True)
            raise DesktopIntegrationError("İçe aktarılan görüntü SHA-256 uyuşmazlığı")
        item={"name":source.name,"file":filename,"sha256":digest,
              "bytes":source.stat().st_size,"camera_origin_verified":False}
        self.data["images"].append(item)
        self.save()
        return item

    def set_calibration(self,path):
        source=Path(path).expanduser().resolve(strict=True)
        if not isinstance(json.loads(source.read_text(encoding="utf-8")),dict):
            raise DesktopIntegrationError("Kalibrasyon JSON nesnesi bekleniyor")
        filename=sha256(source)[:16]+".json"
        shutil.copyfile(source,self.root/"manifests"/filename)
        self.data["calibration"]=filename
        self.save()

    def run(self,module_id,source,*,timeout=120,runner=subprocess.run):
        if module_id not in COMMANDS:
            raise DesktopIntegrationError("Kayıtsız modül")
        if type(timeout)!=int or not 1<=timeout<=7200:
            raise DesktopIntegrationError("Geçersiz zaman aşımı")
        source=Path(source).expanduser().resolve(strict=True)
        image=module_id in IMAGE_ONLY
        if not source.is_file():
            raise DesktopIntegrationError("Girdi dosya olmalıdır")
        if image and source.suffix.lower() not in IMAGE_EXTENSIONS:
            raise DesktopIntegrationError("G01 görüntü girdisi gerektirir")
        if not image:
            if source.suffix.lower()!=".json" or source.stat().st_size>32*1024*1024:
                raise DesktopIntegrationError("Modül JSON ölçüm manifesti gerektirir")
            if not isinstance(json.loads(source.read_text(encoding="utf-8")),dict):
                raise DesktopIntegrationError("JSON manifest kökü nesne olmalıdır")
        n=len(self.data["runs"])+1
        out=self.root/"runs"/f"{n:04d}_{module_id.replace('-','_')}"
        while out.exists():
            n+=1
            out=self.root/"runs"/f"{n:04d}_{module_id.replace('-','_')}"
        out.mkdir()
        command=COMMANDS[module_id]
        argv=([sys.executable,"--cli",command] if getattr(sys,"frozen",False)
              else [sys.executable,"-m","aiforensics",command])
        argv += [str(source)] if image else ["--input",str(source)]
        argv += ["--out",str(out)]
        try:
            result=runner(argv,shell=False,timeout=timeout,capture_output=True,
                          text=True,encoding="utf-8",errors="replace")
            code,stdout,stderr=result.returncode,result.stdout,result.stderr
        except subprocess.TimeoutExpired:
            code,stdout,stderr=124,"","TIMEOUT"
        record={"run_id":out.name,"module_id":module_id,"command":command,
                "input_file":source.name,"input_sha256":sha256(source),
                "state":"SUCCEEDED" if code==0 else "TIMEOUT" if code==124 else "FAILED",
                "returncode":code,
                "validation":"NO_REAL_CAMERA_VALIDATION",
                "decision":"NO_AI_ORIGIN_CONCLUSION",
                "ended_utc":datetime.now(timezone.utc).isoformat()}
        (out/"stdout.txt").write_text(stdout[:100000],encoding="utf-8")
        (out/"stderr.txt").write_text(stderr[:100000],encoding="utf-8")
        atomic_json(out/"execution.json",record)
        self.data["runs"].append(record)
        self.save()
        return record,out

    def artifacts(self):
        return sorted(p for p in (self.root/"runs").rglob("*")
                      if p.is_file() and p.suffix.lower() in
                      {".png",".html",".json",".txt"})

    def export_run(self,run_id,target):
        if run_id not in {r["run_id"] for r in self.data["runs"]}:
            raise DesktopIntegrationError("Projedeki bir çalışma seçilmelidir")
        src=self.root/"runs"/run_id
        files=[p for p in src.rglob("*") if p.is_file()]
        target=Path(target).expanduser().resolve()
        target.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(target,"w",zipfile.ZIP_DEFLATED) as archive:
            for file in files:
                archive.write(file,file.relative_to(src).as_posix())
            manifest={"schema":"fakeproof.export.v1","run":run_id,
                      "decision":"NO_AI_ORIGIN_CONCLUSION",
                      "files":{f.relative_to(src).as_posix():sha256(f) for f in files}}
            archive.writestr("EXPORT_MANIFEST.json",
                             json.dumps(manifest,indent=2,ensure_ascii=False))
        return target
