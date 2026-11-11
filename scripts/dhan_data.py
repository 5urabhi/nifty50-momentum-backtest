"""Read-only local DhanHQ data utility; NEVER places orders.

Usage: python scripts/dhan_data.py --help
Credentials: export DHAN_ACCESS_TOKEN=... in your local terminal.
"""
import argparse
import csv
from pathlib import Path
from urllib.request import Request, urlopen

from index_research.dhan_data import (
    BASE, MASTER_URL, Instrument, build_monthly_close,
    download_candles, read_instruments, save_download
)


def main(argv=None):
    parser=argparse.ArgumentParser(description="Local read-only DhanHQ v2 data import")
    sub=parser.add_subparsers(dest="command",required=True)
    master=sub.add_parser("instrument-master",help="Download official detailed instrument CSV, no token required")
    master.add_argument("--output",default="data/dhan/instrument_master.csv")
    master.add_argument("--max-mb",type=int,default=100)
    fetch=sub.add_parser("download",help="Download OHLCV for explicitly mapped Dhan security IDs")
    fetch.add_argument("--instruments",required=True,help="CSV mapping label,security_id,exchange_segment,instrument")
    fetch.add_argument("--from-date",required=True,help="YYYY-MM-DD inclusive")
    fetch.add_argument("--to-date",required=True,help="YYYY-MM-DD exclusive")
    fetch.add_argument("--output-dir",default="data/dhan/raw")
    fetch.add_argument("--interval",type=int,choices=[1,5,15,25,60],
                       help="Optional intraday candle interval in minutes; omit for daily")
    fetch.add_argument("--pause",type=float,default=.5)
    prepare=sub.add_parser("monthly",help="Convert downloaded daily candles into monthly UNADJUSTED price matrix")
    prepare.add_argument("--instruments",required=True)
    prepare.add_argument("--raw-dir",default="data/dhan/raw")
    prepare.add_argument("--output-dir",default="data/dhan/monthly_research")
    args=parser.parse_args(argv)
    if args.command=="instrument-master":
        dest=Path(args.output)
        if dest.exists():
            parser.error(f"{dest} exists, refusing overwrite")
        dest.parent.mkdir(parents=True,exist_ok=True)
        req=Request(MASTER_URL,headers={"User-Agent":"LocalQuantResearch/1.0"})
        limit=args.max_mb*1024*1024
        if not 1<=args.max_mb<=500:
            parser.error("--max-mb outside 1-500")
        with urlopen(req,timeout=45) as response:
            data=response.read(limit+1)
        if len(data)>limit:
            parser.error("Instrument master exceeds size limit")
        if not data.startswith((b"EXCH_ID",b"SEM_")):
            # Some distributions use UTF-8 BOM or columns in changed order;
            # show a verification warning without leaking the content.
            print("NOTE: verify instrument CSV header/columns against Dhan docs.")
        dest.write_bytes(data)
        print("Downloaded master to",dest)
    elif args.command=="download":
        instruments=read_instruments(args.instruments)
        for inst in instruments:
            print("Downloading",inst.label,inst.exchange_segment,inst.security_id)
            frame=download_candles(inst,args.from_date,args.to_date,
                                   interval=args.interval,pause_seconds=args.pause)
            path,manifest=save_download(frame,inst,args.output_dir,
                                        args.from_date,args.to_date,args.interval)
            print("Saved:",path,"rows:",len(frame),"manifest:",manifest)
        print("RAW CANDLES ARE NOT AN ADJUSTED TOTAL RETURN SERIES.")
    else:
        instruments=read_instruments(args.instruments)
        target=build_monthly_close(args.raw_dir,instruments,args.output_dir)
        print("Monthly UNADJUSTED panel:",target)
        print("Still need independent membership.csv and benchmark.csv; Dhan candles do not supply these.")
if __name__=="__main__":
    main()
