"""Safe local-only Python SDK for QuantLab's documented research HTTP API.

No authentication secrets, no broker orders, and no external host access.
Index runs require explicit confirmation. Data is never silently downloaded.
"""
from __future__ import annotations
from dataclasses import dataclass
import json
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode,urlsplit


class QuantLabRequestError(RuntimeError):
    pass


@dataclass(frozen=True)
class QuantLabClient:
    base_url: str="http://127.0.0.1:8765"
    timeout: float=30.0

    def __post_init__(self):
        parsed=urlsplit(self.base_url)
        if parsed.scheme!="http" or parsed.hostname not in {"127.0.0.1","localhost","::1"} or parsed.username or parsed.password:
            raise ValueError("QuantLab SDK must connect to a loopback HTTP server only")
        if not 0<self.timeout<=3600:
            raise ValueError("Timeout must be positive and bounded")

    def _request(self,method:str,path:str,body:dict|None=None,params:dict|None=None)->dict:
        if not path.startswith("/api/") or ".." in path or "#" in path or "?" in path:
            raise ValueError("Only registered local API paths may be requested")
        url=self.base_url.rstrip("/")+path
        if params:
            url+="?"+urlencode({key:str(value) for key,value in params.items() if value is not None})
        payload=(json.dumps(body,allow_nan=False).encode() if body is not None else None)
        req=Request(url,data=payload,method=method,
                    headers={"Accept":"application/json","Content-Type":"application/json"})
        try:
            with urlopen(req,timeout=self.timeout) as response:
                if response.status!=200:
                    raise QuantLabRequestError("Unexpected HTTP "+str(response.status))
                value=json.loads(response.read(3*1024*1024))
                if not isinstance(value,dict):
                    raise QuantLabRequestError("Expected structured QuantLab JSON response")
                return value
        except HTTPError as exc:
            detail=exc.read(600).decode("utf-8",errors="replace")
            raise QuantLabRequestError(f"QuantLab HTTP {exc.code}: {detail}") from exc

    def health(self)->dict:
        return self._request("GET","/api/health")

    def datasets(self)->list[dict]:
        return self._request("GET","/api/datasets")["datasets"]

    def models(self)->list[dict]:
        return self._request("GET","/api/lab/catalog")["models"]

    def data_passport(self,dataset_id:str)->dict:
        return self._request("GET","/api/workspace/passports/"+_id(dataset_id))

    def index_preflight(self,config:dict)->dict:
        return self._request("POST","/api/workspace/index-studio/preflight",config)

    def run_index(self,config:dict,*,confirm:bool=False)->dict:
        if not confirm:
            raise ValueError("Explicit confirm=True required to launch an index computation")
        preview=self.index_preflight(config)
        if preview["blockers"]:
            raise QuantLabRequestError("Index preflight blocked: "+"; ".join(preview["blockers"]))
        return self._request("POST","/api/workspace/index-studio/run",config)

    def job(self,job_id:str)->dict:
        return self._request("GET","/api/jobs/"+_id(job_id))

    def archived_index_runs(self)->list[dict]:
        return self._request("GET","/api/runs",params={"limit":100})["runs"]

    def explain(self,kind:str,run_id:str,level:str="researcher")->dict:
        if kind not in {"model_run","research_run"}:
            raise ValueError("Use a saved model_run or research_run")
        if level not in {"beginner","researcher","mathematical"}:
            raise ValueError("Invalid explanation level")
        return self._request("GET","/api/workspace/explain/"+kind+"/"+_id(run_id),
                             params={"level":level})

    def why_stock(self,run_id:str,ticker:str|None=None,decision_date:str|None=None)->dict:
        return self._request("GET","/api/workspace/index-studio/decisions/"+_id(run_id),
                             params={"ticker":ticker,"decision_date":decision_date})

    def active_factor_risk(self,run_id:str,lookback:int=36)->dict:
        return self._request("GET","/api/workspace/active-risk/"+_id(run_id),
                             params={"lookback":lookback})

    def methodology(self,run_id:str)->dict:
        return self._request("GET","/api/workspace/methodology/"+_id(run_id))

    def preregister(self,*,question:str,rationale:str,dataset_id:str,primary_metric:str,
                    success_criterion:str,protocol:str)->dict:
        return self._request("POST","/api/workspace/hypotheses",{
            "question":question,"rationale":rationale,
            "planned_dataset_id":dataset_id,"primary_metric":primary_metric,
            "success_criterion":success_criterion,"design":protocol})


def _id(value:str)->str:
    if not isinstance(value,str) or not 1<=len(value)<=90 or not value.replace("_","").replace("-","").isalnum():
        raise ValueError("Invalid local QuantLab identifier")
    return value
