"""Offline research PDF publication from completed local experiment outputs.

Paper is a *draft report*, never an automatically peer-reviewed research claim.
Figures/tables are drawn from the same manifest and CSV as the dashboard.
"""
import json
from html import escape
from pathlib import Path
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether,PageBreak
)


def generate_pdf_report(folder: str | Path) -> Path:
    """Build publication-style PDF; requires reportlab installed locally."""
    root=Path(folder)
    manifest=json.loads((root/"research_manifest.json").read_text())
    config=manifest["config"]
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleLab",parent=styles["Title"],fontSize=19,
                               leading=24,textColor=colors.HexColor("#15304e"),spaceAfter=12))
    styles.add(ParagraphStyle(name="BodyLab",parent=styles["BodyText"],fontSize=9.5,
                               leading=14,spaceAfter=8))
    styles.add(ParagraphStyle(name="NoteLab",parent=styles["BodyText"],fontSize=8.5,
                               leading=12,textColor=colors.HexColor("#7a4d13"),spaceAfter=9))
    styles.add(ParagraphStyle(name="TableLab",parent=styles["BodyText"],fontSize=8,leading=11))
    story=[]
    def p(text,style="BodyLab"):
        story.append(Paragraph(escape(str(text)),styles[style]))
    def heading(text):
        story.append(Spacer(1,0.12*inch))
        story.append(Paragraph(escape(text),styles["Heading2"]))
    def table(rows,widths=None):
        cells=[[Paragraph(escape(str(value)),styles["TableLab"]) for value in row] for row in rows]
        t=Table(cells,colWidths=widths,repeatRows=1,hAlign="LEFT")
        t.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),colors.HexColor("#e2edf6")),
            ("VALIGN",(0,0),(-1,-1),"TOP"),
            ("BOTTOMPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),7),
            ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("LINEBELOW",(0,0),(-1,0),.7,colors.HexColor("#97a9bd")),
            ("LINEBELOW",(0,1),(-1,-1),.3,colors.HexColor("#e4e8ec")),
        ]))
        story.append(t)
    title="Multi-Factor Equity Index Construction: Independent Research Report"
    story.append(Paragraph(title,styles["TitleLab"]))
    p("Experiment: "+config["name"])
    p("Generated: "+manifest.get("generated_utc","unknown"))
    p("DATASTATUS: "+config.get("dataset_status","unverified").upper(),"NoteLab")
    p("RESEARCH-ONLY. This document is not independently audited, is not an MSCI or NSE methodology, and must not be interpreted as verified performance evidence.","NoteLab")
    heading("Executive Summary")
    p("This exploratory study evaluates transparent equity factor ranking, constrained stock selection, index weighting and periodic reconstitution. Performance is measured relative to a supplied benchmark with implementation-cost approximations and chronological evaluation segments. Results remain conditional on data provenance.")
    heading("Research Question and Hypothesis")
    p("Can rules-based combinations of Momentum, Value, Quality, Size and Low Volatility deliver improved benchmark-relative risk-adjusted performance without excessive sector concentration, tracking error or turnover? No superiority claim is made absent rigorous independent holdout validation.")
    heading("Data Sources and Integrity")
    p("Prices cover "+str(manifest["first_price_date"])+" through "+str(manifest["last_price_date"])+". The input dataset is user-supplied or synthetic, and its source declaration is not independent validation.")
    rows=[["Input CSV","SHA-256 fingerprint"]]+[[k," ".join(v[i:i+16] for i in range(0,len(v),16))] for k,v in manifest.get("input_sha256",{}).items()]
    if len(rows)>1:table(rows,[145,360])
    else:p("No dataset fingerprints recorded.")
    heading("Index Methodology")
    desc=[
        ("Factor weights",str(manifest["factor_weights_used"])),
        ("Top N",config["top_n"]),
        ("Weighting",config["weighting"]),
        ("Maximum holding weight",config["max_weight"]),
        ("Sector cap",config.get("sector_cap")),
        ("Rebalance every N months",config["rebalance_every"]),
        ("Cost in basis points",config["cost_bps"]),
        ("Signal execution delay",config["execution_lag"]),
        ("Benchmark",config.get("benchmark_name")),
    ]
    table([["Parameter","Configured rule"]]+desc,[175,330])
    heading("Performance Results by Chronological Segment")
    for segment,values in manifest.get("metrics_by_split",{}).items():
        story.append(Paragraph(escape(segment.replace("_"," ").title()),styles["Heading3"]))
        metrics=[]
        for name,value in values.items():
            if isinstance(value,float):
                display=f"{value:.6g}"
            else:display=str(value)
            metrics.append([name.replace("_"," "),display])
        table([["Statistic","Value"]]+metrics,[320,185])
        story.append(Spacer(1,0.12*inch))
    heading("Concentration and Factor Coverage")
    table([["Diagnostic","Value"]]+[[k,str(v)] for k,v in manifest.get("coverage",{}).items()],
          [320,185])
    heading("Mathematical Basis")
    p("Factor signals are transformed cross-sectionally using clipped z-scores. Index weights satisfy full-investment, long-only stock caps and optional sector constraints. Tracking error is the annualized standard deviation of arithmetic active returns. Information ratio is annualized mean active return divided by tracking error. Portfolio volatility uses the covariance quadratic form w-transpose Sigma w.")
    heading("Statistical and Methodological Limitations")
    for item in manifest.get("limitations",[]):
        p("- "+str(item))
    p("Additional limitations include historical index membership survivorship bias, financial statement publication lags, vendor licensing, corporate actions and delisting payouts, implementation spread and market-impact costs, hyperparameter selection, and data-mining risk. The report does not assert that these issues were solved by parsing a CSV.")
    heading("Research Validation and Next Steps")
    p("Freeze the experiment configuration before the final holdout. Audit historical constituents, benchmark convention, dated fundamentals and corporate actions. Run the complete local test suite and inspect sensitivity to costs, execution delay, sector caps and universe changes. Interpret confidence intervals and statistical tests with multiple-testing adjustments where needed.")
    target=root/"research_paper_draft.pdf"
    doc=SimpleDocTemplate(str(target),pagesize=(612,792),leftMargin=51,rightMargin=51,
                          topMargin=56,bottomMargin=52,title=title,author="Independent Quantitative Research")
    def footer(canvas,document):
        canvas.saveState()
        canvas.setFont("Helvetica",8)
        canvas.setFillColor(colors.HexColor("#60768e"))
        canvas.drawString(51,30,"INDEPENDENT RESEARCH - UNVERIFIED DATA")
        canvas.drawRightString(560,30,f"Page {document.page}")
        canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return target
