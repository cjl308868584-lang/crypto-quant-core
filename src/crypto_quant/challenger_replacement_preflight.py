"""Read-only replacement deployment candidate preflight."""
import hashlib, json, os, platform, stat, subprocess
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path
from jsonschema import Draft202012Validator
from .canonical import canonical_json, stable_id, utc_datetime
from .challenger_replacement_deployment import load_challenger_replacement_deployment
from .challenger_replacement_live_input import _FORBIDDEN_ENVIRONMENT_FRAGMENTS, _LiveTimeTransport
from .challenger_replacement_plan import _strict_json_bytes
from .evidence import artifact_self_hash
from .runtime_health import build_server_time_probe, server_time_probe_reasons, server_time_probe_trust_hash

_COMMANDS = (("git","remote","get-url","origin"),("git","rev-parse","origin/main"),("git","rev-parse","v0.67.0^{}"),("git","status","--porcelain=v1","--untracked-files=all"),("gh","api","repos/cjl308868584-lang/crypto-quant-core","--jq",".permissions.admin"),("/bin/launchctl","print","gui/501/local.crypto-quant.challenger-forward"),("/bin/launchctl","print","gui/501/local.crypto-quant.challenger-replacement-v1"),("/usr/bin/pmset","-g","custom"))

def _now(): return utc_datetime(datetime.now(timezone.utc))
def _machine():
    zone = datetime.now().astimezone().tzinfo
    localtime=os.readlink("/etc/localtime") if Path("/etc/localtime").is_symlink() else ""
    return {"system":platform.system(),"machine":platform.machine(),"uid":os.getuid(),"home":str(Path.home()),"timezone":localtime.split("zoneinfo/")[-1] if "zoneinfo/" in localtime else getattr(zone,"key",str(zone))}
def _run(argv, repository):
    try: result = subprocess.run(tuple(argv),cwd=repository,env={"PATH":"/usr/bin:/bin:/usr/sbin:/sbin"},stdin=subprocess.DEVNULL,capture_output=True,timeout=15,check=False)
    except (OSError,subprocess.SubprocessError) as error: raise ValueError("PREFLIGHT_COMMAND_FAILED") from error
    if len(result.stdout)>65536 or len(result.stderr)>65536: raise ValueError("PREFLIGHT_COMMAND_OUTPUT_OVERSIZED")
    return result.returncode,result.stdout,result.stderr
def _paths_absent(deployment):
    for value in (deployment["paths"]["runtime_root"],deployment["paths"]["target_plist"]):
        target=Path(value)
        if os.path.lexists(target): return False
        for parent in target.parents:
            if not os.path.lexists(parent): continue
            entry=parent.lstat()
            if entry.st_uid not in (0,os.getuid()) or stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode) or stat.S_IMODE(entry.st_mode)&0o022: return False
    return True
def _disk():
    value=os.statvfs(Path.home()); return {"free_bytes":value.f_bavail*value.f_frsize,"free_inodes":value.f_favail}
def _credential_count():
    return sum(any(fragment in name.lower() for fragment in _FORBIDDEN_ENVIRONMENT_FRAGMENTS) for name in os.environ)
def _time_probe():
    probe=build_server_time_probe(transport=_LiveTimeTransport()); trust=server_time_probe_trust_hash(probe)
    if server_time_probe_reasons(probe,trust): raise ValueError("PREFLIGHT_TIME_PROBE_INVALID")
    return {"request_count":3,"trust_hash":trust}
def _transcript(argv, result):
    code,out,err=result; return {"argv":list(argv),"exit_code":code,"stdout_sha256":hashlib.sha256(out).hexdigest(),"stderr_sha256":hashlib.sha256(err).hexdigest()}
def _finish(receipt):
    receipt["receipt_id"]=stable_id("challenger_replacement_preflight",{key:receipt[key] for key in receipt if key not in ("receipt_id","receipt_hash")}); receipt["receipt_hash"]=artifact_self_hash(receipt,"receipt_hash"); return receipt

def load_challenger_replacement_preflight_bytes(data,*,deployment,plist_bytes):
    try:
        receipt=dict(_strict_json_bytes(data)); schema=json.loads(resources.files("crypto_quant").joinpath("schemas","challenger-replacement-preflight-v1.schema.json").read_text())
        binding={key:deployment[key] for key in ("deployment_id","deployment_hash","plist_sha256")}; identity={key:receipt[key] for key in receipt if key not in ("receipt_id","receipt_hash")}
        if data!=canonical_json(receipt).encode() or tuple(Draft202012Validator(schema).iter_errors(receipt)) or receipt["deployment_binding"]!=binding or hashlib.sha256(plist_bytes).hexdigest()!=deployment["plist_sha256"] or receipt["receipt_id"]!=stable_id("challenger_replacement_preflight",identity) or receipt["receipt_hash"]!=artifact_self_hash(receipt,"receipt_hash"): raise ValueError("invalid")
        return receipt
    except (KeyError,TypeError,ValueError) as error:
        raise ValueError("CHALLENGER_REPLACEMENT_PREFLIGHT_BYTES_INVALID") from error

def observe_challenger_replacement_preflight(*,repository:Path,deployment_path:Path,manifest_path:Path):
    deployment=load_challenger_replacement_deployment(deployment_path,manifest_path=manifest_path)
    machine=_machine(); platform_ok=machine=={"system":"Darwin","machine":"arm64","uid":501,"home":"/Users/chenm4","timezone":"Asia/Shanghai"}
    binding={key:deployment[key] for key in ("deployment_id","deployment_hash","plist_sha256")}; authority={"state_write_count":0,"launchctl_mutation_count":0,"credential_count":0,"broker_request_count":0,"order_count":0}
    if not platform_ok:
        return _finish({"$schema":"./challenger-replacement-preflight-v1.schema.json","schema_version":"1.0.0","receipt_id":"challenger_replacement_preflight_"+"0"*64,"receipt_hash":"0"*64,"status":"PREFLIGHT_PLATFORM_UNSUPPORTED","historical_qualification":"NOT_COLLECTED_PLATFORM_UNSUPPORTED","observed_at":_now(),"deployment_binding":binding,"machine":machine,"release":{"origin":"","main":"","tag":"","admin":False,"clean":False},"commands":[],"paths_absent":False,"disk":{"free_bytes":0,"free_inodes":0},"network":{"request_count":0,"trust_hash":"0"*64},"authority":authority,"reason_codes":["PREFLIGHT_PLATFORM_UNSUPPORTED"]})
    results=[_run(argv,Path(repository)) for argv in _COMMANDS]
    text=[item[1].decode("utf-8","strict").strip() for item in results]
    release={"origin":text[0],"main":text[1],"tag":text[2],"admin":text[4]=="true","clean":text[3]==""}
    paths_absent=_paths_absent(deployment); disk=_disk(); credentials=_credential_count(); network={"request_count":0,"trust_hash":"0"*64} if credentials else _time_probe(); reasons=[]; authority["credential_count"]=credentials
    if credentials: reasons.append("PREFLIGHT_CREDENTIAL_BOUNDARY_PRESENT")
    if not (release["origin"]=="https://github.com/cjl308868584-lang/crypto-quant-core.git" and len(release["main"])==40 and release["main"]==release["tag"] and release["admin"] and release["clean"]): reasons.append("PREFLIGHT_RELEASE_IDENTITY_INVALID")
    if not (results[5][0]==113 and results[6][0]==113 and paths_absent): reasons.append("PREFLIGHT_REPLACEMENT_NOT_ABSENT")
    if not (results[7][0]==0 and b" sleep 0" in results[7][1]): reasons.append("PREFLIGHT_POWER_UNSAFE")
    if disk["free_bytes"]<10_000_000_000 or disk["free_inodes"]<100_000: reasons.append("PREFLIGHT_DISK_INSUFFICIENT")
    status="PREFLIGHT_PLATFORM_UNSUPPORTED" if not platform_ok else ("PREFLIGHT_CANDIDATE_INELIGIBLE" if reasons else "PREFLIGHT_CANDIDATE_VERIFIED_NOT_PUBLISHED")
    receipt={"$schema":"./challenger-replacement-preflight-v1.schema.json","schema_version":"1.0.0","receipt_id":"challenger_replacement_preflight_"+"0"*64,"receipt_hash":"0"*64,"status":status,"historical_qualification":"NO_OBSERVABLE_REPLACEMENT_INSTALLATION_AT_COLLECTION","observed_at":_now(),"deployment_binding":binding,"machine":machine,"release":release,"commands":[_transcript(argv,result) for argv,result in zip(_COMMANDS,results)],"paths_absent":paths_absent,"disk":disk,"network":network,"authority":authority,"reason_codes":sorted(reasons)}
    return _finish(receipt)
