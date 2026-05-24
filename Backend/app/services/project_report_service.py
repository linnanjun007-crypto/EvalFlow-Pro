"""ProjectReportService — 14步汇总报告生成、管理、过期清理。"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.project_report import ProjectReport
from app.models.step_output import StepOutput

logger = logging.getLogger(__name__)

REPORT_STORAGE_ROOT = os.environ.get("REPORT_STORAGE_ROOT", "data/reports")

STEP_TITLES = {
    "step1": "项目资料清单",
    "step2": "评价对象概况",
    "step3": "评价指标体系",
    "step4": "评价标准",
    "step5": "数据采集",
    "step6": "数据分析",
    "step7": "综合评分",
    "step8": "问题诊断",
    "step9": "改进建议",
    "step10": "案例对标",
    "step11": "风险评估",
    "step12": "结论摘要",
    "step13": "附录材料",
    "step14": "评价报告",
}


def generate_report(
    db: Session,
    *,
    project_id: str,
    user_id: str,
    retention_days: int = 90,
) -> dict[str, Any]:
    project = db.get(Project, project_id)
    if not project or project.user_id != user_id:
        raise ValueError("项目不存在或无权限")

    outputs = db.scalars(
        select(StepOutput)
        .where(StepOutput.project_id == project_id)
        .order_by(StepOutput.version.desc())
    ).all()
    latest_by_step: dict[str, StepOutput] = {}
    for output in outputs:
        latest_by_step.setdefault(output.step_code, output)

    now = datetime.now(timezone.utc)
    title = f"{project.name} - 完整评价报告"
    parts = [f"# {title}", "", f"> 项目 ID：{project.id}", f"> 生成时间：{now.strftime('%Y-%m-%d %H:%M:%S')}", ""]
    if project.description:
        parts.extend(["## 项目描述", "", project.description, ""])

    for index in range(1, 15):
        step_code = f"step{index}"
        output = latest_by_step.get(step_code)
        step_title = STEP_TITLES.get(step_code, step_code)
        parts.append(f"## Step {index} · {step_title}")
        parts.append("")
        if output and output.content_text:
            parts.append(output.content_text.strip())
        else:
            parts.append("_暂无内容_")
        parts.append("")
        parts.append("---")
        parts.append("")

    content_md = "\n".join(parts)

    existing = db.scalar(
        select(ProjectReport).where(ProjectReport.project_id == project_id, ProjectReport.user_id == user_id)
    )

    user_dir = os.path.join(REPORT_STORAGE_ROOT, user_id)
    os.makedirs(user_dir, exist_ok=True)

    if existing:
        report_id = existing.id
    else:
        report_id = str(uuid4())
    storage_key = os.path.join(user_dir, f"{report_id}.md")

    with open(storage_key, "w", encoding="utf-8") as f:
        f.write(content_md)

    expires_at = now + timedelta(days=retention_days)

    if existing:
        existing.content_md = content_md
        existing.title = title
        existing.project_name = project.name
        existing.storage_key = storage_key
        existing.retention_days = retention_days
        existing.expires_at = expires_at
        existing.generated_at = now
        report = existing
    else:
        report = ProjectReport(
            id=report_id,
            user_id=user_id,
            project_id=project_id,
            project_name=project.name,
            title=title,
            content_md=content_md,
            storage_key=storage_key,
            retention_days=retention_days,
            expires_at=expires_at,
            generated_at=now,
        )
        db.add(report)

    db.commit()
    db.refresh(report)
    return _to_dict(report)


def list_reports(db: Session, user_id: str) -> list[dict[str, Any]]:
    items = db.scalars(
        select(ProjectReport).where(ProjectReport.user_id == user_id).order_by(ProjectReport.generated_at.desc())
    ).all()
    return [_to_dict(r, with_content=False) for r in items]


def get_report(db: Session, report_id: str, user_id: str) -> dict[str, Any]:
    report = db.get(ProjectReport, report_id)
    if not report or report.user_id != user_id:
        raise ValueError("报告不存在或无权限")
    return _to_dict(report, with_content=True)


def delete_report(db: Session, report_id: str, user_id: str) -> None:
    report = db.get(ProjectReport, report_id)
    if not report or report.user_id != user_id:
        raise ValueError("报告不存在或无权限")
    if report.storage_key and os.path.exists(report.storage_key):
        try:
            os.remove(report.storage_key)
        except OSError:
            logger.warning("remove report file failed: %s", report.storage_key)
    db.delete(report)
    db.commit()


def update_retention(db: Session, report_id: str, user_id: str, retention_days: int) -> dict[str, Any]:
    if retention_days < 1 or retention_days > 365:
        raise ValueError("保留天数必须在 1-365 之间")
    report = db.get(ProjectReport, report_id)
    if not report or report.user_id != user_id:
        raise ValueError("报告不存在或无权限")
    report.retention_days = retention_days
    report.expires_at = report.generated_at + timedelta(days=retention_days)
    db.commit()
    db.refresh(report)
    return _to_dict(report, with_content=False)


def cleanup_expired(db: Session) -> int:
    now = datetime.now(timezone.utc)
    expired = db.scalars(select(ProjectReport).where(ProjectReport.expires_at < now)).all()
    count = 0
    for r in expired:
        if r.storage_key and os.path.exists(r.storage_key):
            try:
                os.remove(r.storage_key)
            except OSError:
                pass
        db.delete(r)
        count += 1
    if count:
        db.commit()
    return count


def _to_dict(report: ProjectReport, *, with_content: bool = False) -> dict[str, Any]:
    d = {
        "id": report.id,
        "user_id": report.user_id,
        "project_id": report.project_id,
        "project_name": report.project_name,
        "title": report.title,
        "retention_days": report.retention_days,
        "expires_at": report.expires_at.isoformat() if report.expires_at else None,
        "generated_at": report.generated_at.isoformat() if report.generated_at else None,
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "char_count": len(report.content_md or ""),
    }
    if with_content:
        d["content_md"] = report.content_md
    return d
