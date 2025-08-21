import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
from functools import reduce
from io import BytesIO
import re

# ===================== 通用辅助 =====================

# 这些 key 是各页会用到的统计产物 & 成功提示
# 放在顶部，set_page_config 之后
def shrink_sidebar_uploaders():
    st.markdown("""
    <style>
    /* 命中侧边栏所有 file_uploader 的“拖拽区域” */
    [data-testid="stSidebar"] *[data-testid="stFileUploadDropzone"]{
        padding: 4px 8px !important;
        min-height: 0 !important;
        background: transparent !important;
        border: 1px solid rgba(0,0,0,.1) !important;
    }
    /* 去掉说明文字与图标，只留右侧按钮 */
    [data-testid="stSidebar"] *[data-testid="stFileUploadDropzone"] p,
    [data-testid="stSidebar"] *[data-testid="stFileUploadDropzone"] small,
    [data-testid="stSidebar"] *[data-testid="stFileUploadDropzone"] svg{
        display: none !important;
    }
    /* 进一步压缩内部边距 */
    [data-testid="stSidebar"] *[data-testid="stFileUploadDropzone"] section{
        padding: 0 !important; margin: 0 !important; gap: 0 !important;
    }
    /* 防止按钮因为换行变高（不同版本 testid 可能不同，统一收紧） */
    [data-testid="stSidebar"] button[kind="secondary"]{
        min-height: 32px !important;
        padding: 2px 10px !important;
    }
    </style>
    """, unsafe_allow_html=True)

def compact_sidebar_uploader():
    st.markdown("""
    <style>
    /* 仅影响侧边栏的 file_uploader */
    [data-testid="stSidebar"] div[data-testid="stFileUploadDropzone"]{
        padding: 4px 8px !important;         /* 上下左右更小的内边距 */
        min-height: 44px !important;          /* 控件整体更矮 */
        background: var(--secondary-background-color) !important;
    }
    [data-testid="stSidebar"] div[data-testid="stFileUploadDropzone"] section{
        padding: 0 !important; margin: 0 !important; gap: 6px !important;
    }
    [data-testid="stSidebar"] div[data-testid="stFileUploadDropzone"] p{
        margin: 0 !important; font-size: 12px !important; line-height: 1.1 !important;
    }
    [data-testid="stSidebar"] div[data-testid="stFileUploadDropzone"] svg{
        width: 16px !important; height: 16px !important;
    }
    </style>
    """, unsafe_allow_html=True)
def ultra_compact_sidebar_uploader():
    st.markdown("""
    <style>
    [data-testid="stSidebar"] div[data-testid="stFileUploadDropzone"]{
        padding: 2px 6px !important;
        min-height: 36px !important;
        background: transparent !important; border: 1px solid rgba(0,0,0,.08) !important;
    }
    [data-testid="stSidebar"] div[data-testid="stFileUploadDropzone"] section{
        padding: 0 !important; margin: 0 !important; gap: 4px !important;
    }
    [data-testid="stSidebar"] div[data-testid="stFileUploadDropzone"] p,
    [data-testid="stSidebar"] div[data-testid="stFileUploadDropzone"] small{
        font-size: 11px !important; line-height: 1 !important; margin: 0 !important;
    }
    [data-testid="stSidebar"] div[data-testid="stFileUploadDropzone"] svg{
        width: 14px !important; height: 14px !important;
    }
    </style>
    """, unsafe_allow_html=True)

def set_sidebar_width(px: int = 360):
    st.markdown(f"""
    <style>
    /* 只在桌面端固定宽度，移动端保持自适应 */
    @media (min-width: 992px) {{
      [data-testid="stSidebar"] {{
        min-width: {px}px !important;
        max-width: {px}px !important;
      }}
    }}
    </style>
    """, unsafe_allow_html=True)

def _can_run_now():
    """读取 session_state，判断是否允许执行统计。"""
    filter_ok = st.session_state.get("filter_file") is not None
    any_checked = any(
        (st.session_state.get(f"{k}:use", False) and st.session_state.get(k) is not None)
        for k in FILE_SLOTS.keys() if k != "filter_file"
    )
    return filter_ok, any_checked, (filter_ok and any_checked)

def render_topbar_controls():
    st.markdown("### ⚙️ 统计参数")
    bar_left, bar_right = st.columns([3, 1])

    with bar_left:
        st.date_input("统计基准日期", datetime.today(), key="as_of")
        filter_ok, any_checked, can_run = _can_run_now()
        # 友好提示
        if not filter_ok:
            pass
        elif not any_checked:
            pass
        else:
            show_persistent_success()  # 若签名一致，显示“统计完成”

    with bar_right:
        # 顶部栏按钮（你已有）：
        if st.button("🚀 执行统计", key="_btn_run_top", use_container_width=True, disabled=not can_run):
            st.session_state["_do_run"] = True
            _clear_all_results()   # 保险



RESULT_KEYS = [
    "trad_res","batch_res","baohan_res","daichang_res",
    "trad_overdue","batch_overdue","df_daichang",
    "final_all_res",            # 分类汇总页最后总表
    "_last_success_sig",        # 你自己的“统计完成”提示签名
]

from contextlib import contextmanager

# 存取：上次执行日志（按步骤保存 title/state/lines）
def _logs() -> dict:
    return st.session_state.setdefault("_last_run_logs", {})

def _reset_logs_for_new_run():
    st.session_state["_run_id"] = st.session_state.get("_run_id", 0) + 1
    st.session_state["_last_run_logs"] = {}

def _clear_all_results():
    for k in [
        "trad_res","batch_res","baohan_res","daichang_res",
        "trad_overdue","batch_overdue","df_daichang",
        "final_all_res","_last_success_sig",
        "_last_run_logs",        # ← 勾选/上传变化时连日志一起清空
    ]:
        st.session_state.pop(k, None)

@contextmanager
def status_log(step_key: str, label: str, *, expanded=True, state="running", **kwargs):
    """
    和 st.status 一样用，但会把日志内容快照到 session_state 里，供切页重绘。
    用法:
        with status_log("baohan", "读取保函…") as (log, done):
            log("• xxx")
            done("保函统计完成", "complete")
    """
    run_id = st.session_state.get("_run_id", 0)
    rec = {"title": label, "state": state, "expanded": expanded, "lines": []}
    _logs()[step_key] = rec
    with st.status(label, expanded=expanded, state=state, key=f"run{run_id}:{step_key}", **kwargs) as s:
        def log(msg: str):
            rec["lines"].append(msg)
            st.write(msg)
        def done(new_label: str, new_state: str = "complete", new_expanded: bool | None = False):
            rec["title"] = new_label
            rec["state"] = new_state
            if new_expanded is not None:
                rec["expanded"] = new_expanded
            s.update(label=new_label, state=new_state, expanded=new_expanded)
        yield log, done

def render_saved_logs(header: str = "📝 上次执行日志"):
    """不执行计算，仅把上一次的日志快照重绘出来。"""
    logs = st.session_state.get("_last_run_logs")
    if not logs:
        return
    st.markdown(f"#### {header}")
    order = ["baohan", "batch", "trad", "daichang"]
    for key in order:
        rec = logs.get(key)
        if not rec:
            continue
        with st.status(rec["title"], state=rec["state"], expanded=False, key=f"saved:{key}:{st.session_state.get('_run_id',0)}"):
            for line in rec.get("lines", []):
                st.write(line)

def _on_use_toggle(base_key: str):
    # 只要勾选变化 → 清空结果 + 清空日志
    _clear_all_results()
    _invalidate_success()

def _on_upload_change(base_key: str, source_suffix: str = "uploader_sb"):
    uf = st.session_state.get(f"{base_key}:{source_suffix}")
    if uf is not None:
        st.session_state[base_key] = BytesIO(uf.getvalue())
        st.session_state[f"{base_key}:filename"] = getattr(uf, "name", "")
        st.session_state[f"{base_key}:use"] = True
    else:
        for k in [base_key, f"{base_key}:filename", f"{base_key}:use"]:
            st.session_state.pop(k, None)
    _clear_all_results()
    _invalidate_success()

def _invalidate_success():
    st.session_state.pop("_last_success_sig", None)


def _toggle_sidebar_uploader(base_key: str):
    st.session_state[f"{base_key}:show_upload"] = not st.session_state.get(f"{base_key}:show_upload", False)

def uploader_box(title: str, key: str, *, type_=("xlsx",), help: str | None = None):
    """
    - 未上传 或 未勾选参与统计(:use=False)：显示 st.file_uploader
    - 已上传 且 勾选参与统计(:use=True)：隐藏上传器，仅显示“已上传：文件名”
    - 容器总高度固定，避免页面跳动
    返回：BytesIO 或 None
    """
    TITLE_H = 0
    BODY_MIN_H = 84
    GAP_H = 4

    with st.container(border=True):
        st.markdown(f"**{title}**")

        uploaded = st.session_state.get(key) is not None
        fname    = st.session_state.get(f"{key}:filename", "")
        active   = st.session_state.get(f"{key}:use", True)  # ← 新增：是否参与统计（勾选状态）
        show_uploader = (not uploaded) or (not active)       # ← 新增：未上传 或 未勾选 → 显示上传器

        body = st.empty()
        pad  = st.empty()

        if show_uploader:
            # 显示上传器（未上传 或 想更换文件时）
            body.file_uploader(
                "", type=type_, key=f"{key}:uploader",
                label_visibility="collapsed", help=help,
                on_change=_on_upload_change, args=(key,)
            )
            pad.markdown(f"<div style='height:{GAP_H}px;'></div>", unsafe_allow_html=True)

            # 如果已有缓存但未勾选，把文件名用灰字提示一下（可选）
            if uploaded and fname:
                st.markdown(
                    f"<div style='font-size:12px;color:rgba(49,51,63,.6);margin-top:-6px;'>"
                    f"（已缓存：{fname}，重新上传将覆盖）</div>",
                    unsafe_allow_html=True
                )
        else:
            # 隐藏上传器，只显示文件名（已上传且勾选参与统计）
            body.markdown(
                f"<div style='min-height:{BODY_MIN_H}px; display:flex; align-items:center;'>"
                f"<span style='font-size:13px;color:rgba(49,51,63,.7)'>{fname}</span>"
                f"</div>", unsafe_allow_html=True
            )
            pad.markdown(f"<div style='height:{GAP_H}px;'></div>", unsafe_allow_html=True)

        return st.session_state.get(key)

def _on_use_toggle(base_key: str):
    # 如需“取消勾选时顺便清掉文件缓存”，可在此处 pop 掉 {base_key} 等
    # 当前只清结果，保留已上传的文件，方便你快速切换
    _clear_all_results()
    _invalidate_success()


def get_cached_file(key: str):
    """在其它页面还原 BytesIO；无缓存返回 None。"""
    b = st.session_state.get(f"{key}:bytes")
    return BytesIO(b) if b else None

def forever_expiredate(x):
    try:
        dt = pd.to_datetime(x, errors="raise")
        return dt
    except Exception:
        return pd.Timestamp.max
def extractsheet_taizhang(xl: pd.ExcelFile) -> str:
    for name in xl.sheet_names:
        if ("台账" in name) or ("总台账" in name):
            return name
    return xl.sheet_names[0]
def extractsheet(xl: pd.ExcelFile) -> str:
    """直接返回第一张表名"""
    return xl.sheet_names[0]
def extractsheet_baohan(xl: pd.ExcelFile) -> str:
    for name in xl.sheet_names:
        if ("保函" in name) or ("非融" in name):
            return name
    return xl.sheet_names[0]
def extractsheet_daichang(xl: pd.ExcelFile) -> str:
    for name in xl.sheet_names:
        if ("代偿" in name):
            return name
    return xl.sheet_names[0]
def _clean_columns(df: pd.DataFrame) -> pd.DataFrame:
    df.columns = (
        df.columns
        .str.replace(r"\s+", "", regex=True)
        .str.replace(r"[（(]\s*(?:万元|%|元)\s*[）)]", "", regex=True)
        .str.replace("（", "(", regex=False)
        .str.replace("）", ")", regex=False)
    )
    return df

# ===================== 数据读取 =====================

# ==========================================
AGG_MAP_BAOHAN = {
    "在保余额": ("在保余额", "sum"),
    "笔数": (None, "count"),
    "户数": ("客户名称", "nunique"),
    "责任余额": ("责任余额", "sum"),
    "放款金额": ("放款金额", "sum"),
}

def calc_baohan_metrics(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    y0, y1 = as_of.replace(month=1, day=1), as_of.replace(month=12, day=31)
    m0, m1 = as_of.replace(day=1), (as_of.replace(day=1) + pd.offsets.MonthEnd(0))
    ly0, ly1 = y0 - pd.DateOffset(years=1), y1 - pd.DateOffset(years=1)

    # 合同到期时间如果写了文字而不是时间（例：无固定到期日，保全解除之日），视为无穷远的日期

    RULES = {
        "当年": lambda d: d["放款时间"].between(y0, y1) & (d["放款金额"] > 0),
        "当月": lambda d: d["放款时间"].between(m0, m1) & (d["放款金额"] > 0),
        "上一年": lambda d: d["放款时间"].between(ly0, ly1) & (d["放款金额"] > 0),
        "在保": lambda d: (d["在保余额"] > 0) & (
            d["合同到期时间"].apply(forever_expiredate) > as_of_dt
        ),
        "保函": lambda d: d["客户名称"] != "合计"
    }

    metrics = [
        "保函_在保_在保余额",
        "保函_当年_放款金额",
    ]

    def _c(name):
        *keys, agg = name.split("_")
        mask = reduce(lambda a, b: a & b, [RULES[k](df) for k in keys], pd.Series(True, index=df.index))
        mapper = AGG_MAP_BAOHAN[agg]
        if callable(mapper):
            return mapper(df.loc[mask])
        col, how = mapper
        if how == "sum":
            return df.loc[mask, col].sum()
        if how == "count":
            return int(mask.sum())
        if how == "nunique":
            return df.loc[mask, col].nunique()

    base_res = {m: _c(m) for m in metrics}
    return pd.Series({**base_res}, name="保函业务")
# ==========================================
AGG_MAP_DAICHANG = {
    "代偿金额": lambda df: df["代偿金额"].sum() 
}

def calc_daichang_metrics(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:

    y0, y1 = as_of.replace(month=1, day=1), as_of.replace(month=12, day=31)
    m0, m1 = as_of.replace(day=1), (as_of.replace(day=1) + pd.offsets.MonthEnd(0))
    ly0, ly1 = y0 - pd.DateOffset(years=1), y1 - pd.DateOffset(years=1)
    RULES = {
        "当年": lambda d: d["代偿时间"].between(y0, y1) & (d["代偿金额"] > 0),
        "代偿": lambda d: ~d["企业名称"].astype(str).str.contains("代偿项目", na=False),
        "小微": lambda d: d["政策扶持领域"].astype(str).str.contains("小微企业", na=False)
    }

    metrics = ["代偿_当年_代偿金额","代偿_代偿金额","代偿_当年_小微_代偿金额"
    ]

    def _c(name):
        *keys, agg = name.split("_")
        mask = reduce(lambda a, b: a & b, [RULES[k](df) for k in keys], pd.Series(True, index=df.index))
        mapper = AGG_MAP_DAICHANG[agg]
        if callable(mapper):
            return mapper(df.loc[mask])
        col, how = mapper
        if how == "sum":
            return df.loc[mask, col].sum()
        if how == "count":
            return int(mask.sum())
        if how == "nunique":
            return df.loc[mask, col].nunique()

    base_res = {m: _c(m) for m in metrics}
    return pd.Series({**base_res}, name="代偿明细")
# ==========================================




def calc_trad_metrics(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    y0, y1 = as_of.replace(month=1, day=1), as_of.replace(month=12, day=31)
    m0, m1 = as_of.replace(day=1), (as_of.replace(day=1) + pd.offsets.MonthEnd(0))
    ly0, ly1 = y0 - pd.DateOffset(years=1), y1 - pd.DateOffset(years=1)
    AGG_MAP_TRAD = {
    "名义放款": ("放款金额", "sum"),
    "实际放款": ("实际放款", "sum"),
    "在保余额": ("在保余额", "sum"),
    "笔数": (None, "count"),
    "户数": ("客户名称", "nunique"),
    "责任余额": ("责任余额", "sum"),
    "名义放款": ("放款金额", "sum"),
    "名义在保余额": ("名义在保余额", "sum"),
    "担保费": ("担保费/利息", "sum"),
}
    y0, y1 = as_of.replace(month=1, day=1), as_of.replace(month=12, day=31)
    m0, m1 = as_of.replace(day=1), (as_of.replace(day=1) + pd.offsets.MonthEnd(0))
    ly0, ly1 = y0 - pd.DateOffset(years=1), y1 - pd.DateOffset(years=1)

    df_t_sum_zaibao = (
        df.groupby("客户名称", as_index=False)["在保余额"]
                .sum().rename(columns={"在保余额": "客户在保余额"})
    )
    df_t_sum_zeren = (
        df.groupby("客户名称", as_index=False)["责任余额"]
            .sum().rename(columns={"责任余额": "客户责任余额"})
    )
    nameset500_t_zaibao = set(
        df_t_sum_zaibao.loc[df_t_sum_zaibao["客户在保余额"] <= 500, "客户名称"]
    )
    nameset10_t_zeren = set(
        df_t_sum_zeren.nlargest(10, "客户责任余额")["客户名称"]
    )
    nameset1_t_zeren = set(
        df_t_sum_zeren.nlargest(1, "客户责任余额")["客户名称"]
    )
    # 打印出 set_t_500_zaibao
    #check#st.text(f"单户在保余额<500万客户: {nameset500_t_zaibao}")
    #check#st.text(f"责任前10客户: {nameset10_t_zeren}")
    # 打印前10客户及其责任余额表格
    df_top10 = df_t_sum_zeren[df_t_sum_zeren["客户名称"].isin(nameset10_t_zeren)].sort_values("客户责任余额", ascending=False)
    #st.dataframe(df_top10, use_container_width=True)                                                                           #check
    #check#st.text(f"责任最大客户: {nameset1_t_zeren}")
    RULES = {
        "当年":  lambda d: d["放款时间"].between(y0,  y1)  & (d["放款金额"] > 0),
        "当月":  lambda d: d["放款时间"].between(m0, m1) & (d["放款金额"] > 0),
        "本月解保": lambda d: d["实际到期时间"].between(m0, m1),
        "本年解保": lambda d: d["实际到期时间"].between(y0,  y1),
        "在保":  lambda d: d["在保余额"] > 0,
        "传统":  lambda d: d["业务品种2"].isin(["传统"]),
        "全担":  lambda d: d["公司责任风险比例"] == "100%",
        "惠蓉贷": lambda d: d["业务品种3"] == "惠蓉贷",
        "驿享贷": lambda d: d["业务品种"]  == "驿享贷",
        "担保费率低于1%(含)": lambda d: d["担保费率/利率"] <= 1,
        "小微":  lambda d: d["企业类别"].isin(["小型","微型"]) & (d["业务品种"] != "惠抵贷"),
        "中型":  lambda d: d["企业类别"] == "中型",
        "三农":  lambda d: d["企业类别"] == "三农",
        "中小":  lambda d: d["企业类别"].isin(["小型","微型","中型"]),
        "支农支小": lambda d: d["企业类别"].isin(["小型","微型","三农"]),
        "个体工商户及小微企业主": lambda d: d["业务品种"] == "惠抵贷",
        "广义小微": lambda d: d["企业类别"].isin(["小型", "微型"]) | d["业务品种"] == "惠抵贷",
        "农户及新型农业经营主体":     lambda d: d["企业类别"].isin(["三农"]),
        "新增":  lambda d: d["新增/续贷"] == "新增",
        "民企":  lambda d: d["国企民企"] == "民企",
        "国企":  lambda d: d["国企民企"] == "国企",
        "上一年": lambda d: d["放款时间"].between(ly0, ly1) & (d["放款金额"] > 0),
        "不良": lambda d: d["风险等级"].isin(["次级","可疑","损失"]),
        "单户在保<=500": lambda d: d["客户名称"].isin(nameset500_t_zaibao),
        "单户责任前10": lambda d: d["客户名称"].isin(nameset10_t_zeren),
        "单户责任最大": lambda d: d["客户名称"].isin(nameset1_t_zeren),
    }
    RULES.update({lvl: (lambda d, _lvl=lvl: d["风险等级"] == _lvl)
                  for lvl in ["正常","关注","次级","可疑","损失"]})

    指标列表 = [
    "传统_当年_名义放款", "传统_当年_中型_名义放款", "传统_当年_小微_名义放款",
    "传统_当年_实际放款", "传统_中小_当年_实际放款","传统_小微_当年_实际放款",
    "传统_上一年_实际放款", "传统_上一年_户数","传统_中小_当年_户数","传统_小微_当年_户数","传统_当月_实际放款",
    "传统_当年_户数", "传统_当年_小微_户数", "传统_当年_笔数", 
    "传统_中小_当年_笔数","传统_小微_当年_笔数",
    "传统_中小_在保_在保余额", "传统_中型_在保余额", "传统_在保_在保余额", "传统_小微_在保_在保余额",

    "新增_传统_当年_实际放款","新增_传统_当年_名义放款",
    "新增_传统_当年_支农支小_名义放款", "新增_传统_当年_支农支小_全担_名义放款",
    "新增_传统_当年_支农支小_惠蓉贷_名义放款", "新增_传统_当年_支农支小_户数",

    "传统_当年_支农支小_名义放款","传统_当年_支农支小_实际放款","传统_当年_支农支小_户数",

    "传统_在保_名义在保余额","传统_在保_在保余额","传统_在保_户数",
    "传统_广义小微_在保_户数", "传统_广义小微_在保_在保余额",
    "传统_当年_支农支小_全担_名义放款", "传统_当年_支农支小_惠蓉贷_名义放款",
    "新增_传统_当年_民企_名义放款", "新增_传统_当年_民企_实际放款", "新增_传统_当年_民企_户数",
    "传统_当年_民企_名义放款", "传统_当年_民企_实际放款", "传统_当年_民企_户数",
    "传统_小微_在保_户数",

    "传统_个体工商户及小微企业主_实际放款","传统_个体工商户及小微企业主_在保_在保余额", "传统_个体工商户及小微企业主_在保_户数",
    "传统_农户及新型农业经营主体_实际放款","传统_农户及新型农业经营主体_在保_在保余额", "传统_农户及新型农业经营主体_在保_户数",
    "传统_支农支小_在保_在保余额", "传统_支农支小_在保_户数",
    "传统_担保费率低于1%(含)_在保_在保余额", "传统_本月解保_在保余额", "传统_本年解保_在保余额",
    "传统_当年_驿享贷_名义放款",
    "传统_在保_责任余额","传统_在保_担保费","传统_在保_名义放款",
    "传统_在保_三农_责任余额",
    "传统_三农_单户在保<=500_责任余额","传统_小微_单户在保<=500_责任余额","传统_小微_单户在保<=500_在保_担保费","传统_小微_单户在保<=500_在保_名义放款",
    "传统_单户责任前10_责任余额","传统_单户责任最大_责任余额",
    ] + [f"传统_{lvl}_在保余额" for lvl in ["正常","关注","次级","可疑","损失"]]

    def _c(name):
        *keys, agg = name.split("_")
        mask = reduce(lambda a, b: a & b, [RULES[k](df) for k in keys], pd.Series(True, index=df.index))
        mapper = AGG_MAP_TRAD[agg]
        if callable(mapper):
            return mapper(df.loc[mask])
        col, how = mapper
        if how == "sum":
            return df.loc[mask, col].sum()
        if how == "count":
            return int(mask.sum())
        if how == "nunique":
            return df.loc[mask, col].nunique()
        
    base_res = {n: _c(n) for n in 指标列表}



    # ── ③ 合并并返回 ──────────────────────────────────────────
    return pd.Series({**base_res}, name="传统业务")


# ===================== 批量指标计算 =====================




def calc_batch_metrics(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    y0, y1 = as_of.replace(month=1, day=1), as_of.replace(month=12, day=31)
    m0, m1 = as_of.replace(day=1), (as_of.replace(day=1) + pd.offsets.MonthEnd(0))
    ly0, ly1 = y0 - pd.DateOffset(years=1), y1 - pd.DateOffset(years=1)

    df_b_sum_zaibao = (
        df.groupby("债务人证件号码", as_index=False)["在保余额"]
                .sum().rename(columns={"在保余额": "客户在保余额"})
    )
    df_b_sum_zeren = (
        df.groupby("债务人证件号码", as_index=False)["责任余额"]
                .sum().rename(columns={"责任余额": "客户责任余额"})
    )
    nameset500_b_zaibao = set(
        df_b_sum_zaibao.loc[df_b_sum_zaibao["客户在保余额"] <= 500, "债务人证件号码"]
    )
    nameset200_b_zaibao = set(
        df_b_sum_zaibao.loc[df_b_sum_zaibao["客户在保余额"] <= 200, "债务人证件号码"]
    )
    nameset10_b_zeren = set(
        df_b_sum_zeren.nlargest(10, "客户责任余额")["债务人证件号码"]
    )
    nameset1_b_zeren = set(
        df_b_sum_zeren.nlargest(1, "客户责任余额")["债务人证件号码"]
    )
    # 打印出 seb_b_500_zaibao

    #check#st.text(f"责任前10客户: {nameset10_b_zeren}")
    # 打印前10客户及其责任余额表格
    df_top10 = df_b_sum_zeren[df_b_sum_zeren["债务人证件号码"].isin(nameset10_b_zeren)].sort_values("客户责任余额", ascending=False)
    #st.dataframe(df_top10, use_container_width=True)           #check
    #check#st.text(f"责任最大客户: {nameset1_b_zeren}")
    #check#st.text(f"所有列名: {list(df.columns)}")

    
    AGG_MAP_BATCH = {
    "名义放款": ("主债权金额", "sum"),
    "实际放款": ("实际放款", "sum"),
    "责任余额": ("责任余额", "sum"),
    "在保余额": ("在保余额", "sum"),
    "名义在保余额": ("在保余额", "sum"),
    "笔数": (None, "count"),
    "户数": ("债务人证件号码", "nunique"),
    "担保费": ("担保费", "sum"),
}
    RULES = {
        "上一年": lambda d: d["主债权起始日期"].between(ly0, ly1) & (d["主债权金额"] > 0),
        "当年": lambda d: d["主债权起始日期"].between(y0, y1) & (d["主债权金额"] > 0),
        "当月": lambda d: d["主债权起始日期"].between(m0, m1) & (d["主债权金额"] > 0),
        "在保": lambda d: d["是否已解保"] == "在保",
        "批量": lambda d: d["业务品种2"].isin(["批量"]),
        "全担": lambda d: d["分险比例(直担)"] == 100,
        "担保费率低于1%(含)": lambda d: d["担保年费率"] <= 1,
        "中型": lambda d: d["企业划型"] == "中型企业",
        "小微": lambda d: d["企业划型"].isin(["小型企业", "微型企业"]),
        "中小": lambda d: d["企业划型"].isin(["小型企业", "微型企业", "中型企业"]),
        "企业": lambda d: d["债务人类别"] == "企业/企业",
        "个人": lambda d: d["债务人类别"] != "企业/企业",
        "三农": lambda d: d["政策扶持领域"].str.contains("三农", na=False),
        "农业": lambda d: d["所属行业(工)"] == "农、林、牧、渔业",
        "非农小微": lambda d: (
            d["企业划型"].isin(["小型企业", "微型企业"]) & (d["所属行业(工)"] != "农、林、牧、渔业")
        ),
        "农业小微": lambda d: (
            d["企业划型"].isin(["小型企业", "微型企业"]) & (d["所属行业(工)"] == "农、林、牧、渔业")
        ),
        "非农小微和小微企业主": lambda d: (
            (d["企业划型"].isin(["小型企业", "微型企业"]) | d["债务人类别"].isin(["个人/个体工商户", "个人/小微企业主"])) & (d["所属行业(工)"] != "农、林、牧、渔业")
        ),
        #d["企业划型"].d["债务人类别"].isin(["个人/个体工商户", "个人/小微企业主"]) & (d["所属行业(工)"] != "农、林、牧、渔业")
        "支农支小": lambda d: d["政策扶持领域"].isin(["三农", "小微企业", "小微企业,三农"]),
        "个体工商户及小微企业主": lambda d: d["债务人类别"].isin(["个人/个体工商户", "个人/小微企业主"]),
        "广义小微": lambda d: d["企业划型"].isin(["小型企业", "微型企业"]) | d["债务人类别"].isin(["个人/个体工商户", "个人/小微企业主"]),
        "城镇居民": lambda d: d["债务人类别"].isin(["个人/个体工商户"]),
        "农户": lambda d: d["债务人类别"].isin(["个人/农户"]),
        "首贷户": lambda d: d.get("首贷户", pd.Series([False]*len(d))) == "是",
        "本月解保": lambda d: d["主债权到期日期"].between(m0, m1),
        "本年解保": lambda d: d["主债权到期日期"].between(y0, y1),
        "民企": lambda d: d["债务人经营主体经济成分"].str.contains("私人控股", na=False),
        "国企": lambda d: d["债务人经营主体经济成分"].str.contains("国有控股", na=False),
        "科创": lambda d: d["担保产品"].str.contains("科创", na=False),
        "单户在保<=500": lambda d: d["债务人证件号码"].isin(nameset500_b_zaibao),
        "单户在保<=200": lambda d: d["债务人证件号码"].isin(nameset200_b_zaibao),
        "单户责任前10": lambda d: d["债务人证件号码"].isin(nameset10_b_zeren),
        "单户责任最大": lambda d: d["债务人证件号码"].isin(nameset1_b_zeren),
    }

    metrics = [
        "批量_当年_名义放款",
        "批量_当年_中型_名义放款",
        "批量_当年_小微_名义放款",
        "批量_当年_小微_户数",
        "批量_当年_笔数",
        "批量_当年_小微_笔数",
        "批量_中小_在保_在保余额",
        "批量_中型_在保_在保余额",
        "批量_当年_实际放款",
        "批量_上一年_实际放款",
        "批量_中小_当年_实际放款",
        "批量_当年_户数",
        "批量_中小_当年_户数",
        "批量_小微_当年_户数",
        "批量_中小_当年_笔数",
        "批量_小微_当年_笔数",
        "批量_上一年_户数",
        "批量_在保_名义在保余额",
        "批量_在保_在保余额",

        "批量_在保_户数",
        "批量_在保_企业_户数",
        "批量_在保_个人_户数",
        "批量_在保_非农小微_户数",
        "批量_在保_非农小微_在保余额",  
        "批量_在保_农业小微_户数",
        "批量_在保_农业小微_在保余额",
        "批量_首贷户_在保_户数",
        "批量_首贷户_在保_在保余额",
        "批量_广义小微_在保_户数",
        "批量_广义小微_在保_在保余额",
        "批量_个体工商户及小微企业主_实际放款",
        "批量_个体工商户及小微企业主_在保_在保余额",
        "批量_个体工商户及小微企业主_在保_户数",
        "批量_农户_实际放款",
        "批量_农户_在保_在保余额",
        "批量_农户_在保_户数",
        "批量_在保_三农_责任余额",
        "批量_当年_支农支小_名义放款",
        "批量_当年_支农支小_实际放款",
        "批量_当年_支农支小_户数",
        "批量_支农支小_在保_在保余额",
        "批量_支农支小_在保_户数",
        "批量_当年_民企_名义放款",
        "批量_当年_民企_实际放款",
        "批量_当年_民企_户数",
        "批量_担保费率低于1%(含)_在保_在保余额",
        "批量_当年_科创_实际放款",
        "批量_科创_在保_在保余额",
        "批量_科创_在保_户数",
        "批量_当年_科创_户数",
        "批量_城镇居民_在保_在保余额",
        "批量_城镇居民_在保_户数",
        "批量_当月_实际放款",
        "批量_三农_单户在保<=500_责任余额","批量_农户_单户在保<=200_责任余额","批量_小微_单户在保<=500_责任余额","批量_小微_单户在保<=500_在保_担保费","批量_小微_单户在保<=500_在保_名义放款",
        "批量_单户责任前10_责任余额","批量_单户责任最大_责任余额",
        "批量_在保_责任余额","批量_在保_担保费","批量_在保_名义放款",
    ]

    def _c(name):
        *keys, agg = name.split("_")
        mask = reduce(lambda a, b: a & b, [RULES[k](df) for k in keys], pd.Series(True, index=df.index))
        mapper = AGG_MAP_BATCH[agg]
        if callable(mapper):
            return mapper(df.loc[mask])
        col, how = mapper
        if how == "sum":
            return df.loc[mask, col].sum()
        if how == "count":
            return int(mask.sum())
        if how == "nunique":
            return df.loc[mask, col].nunique()

    # 原有指标 
    base_res = {m: _c(m) for m in metrics}

    # ==== 3. 合并并返回 ====
    return pd.Series({**base_res}, name="批量业务")



FILE_SLOTS = {
    "filter_file":   "筛选条件---(必选)",
    "trad_file":     "传统",
    "batch_file":    "批量",
    "baohan_file":   "保函",
    "daichang_file": "代偿",
}

def render_status_sidebar():
              # 主区顶部：日期 + 执行按钮（依赖 sidebar 的状态）

    with st.sidebar:

        render_topbar_controls()
        st.subheader("📑 页面导航")
        page = st.radio("", ["工作日志","报表", "在保余额检查"], label_visibility="collapsed", key="_nav_page")

        st.subheader("📦 上传文件")

        used_map = {}
        for key, label in FILE_SLOTS.items():
            uploaded = st.session_state.get(key) is not None
            use_key  = f"{key}:use"
            fname    = st.session_state.get(f"{key}:filename", "")

            c1, c2 = st.columns([2, 3])
            with c1:
                if key == "filter_file":
                    st.checkbox(label, value=True, disabled=True, key=f"{key}:lock")
                    st.session_state[use_key] = True
                else:
                    if uploaded:
                        st.checkbox(label, key=use_key, on_change=_on_use_toggle, args=(key,))
                    else:
                        st.checkbox(label, key=f"{key}:phantom", disabled=True, value=False)

            with c2:

                # 每行下方直接放原生 uploader（一次点击）
                st.file_uploader(
                    label="", type=("xlsx",), key=f"{key}:uploader_sb",
                    label_visibility="collapsed", accept_multiple_files=False,
                    on_change=_on_upload_change, args=(key, "uploader_sb"),
                    width=200,
                )

            if key != "filter_file":
                used_map[key] = uploaded and st.session_state.get(use_key, False)

    return page

# 用参与统计的关键输入生成一个“签名”
def _current_signature() -> str:
    parts = [str(st.session_state.get("as_of"))]  # 统计基准日期也纳入
    for key in ["filter_file", "trad_file", "batch_file", "baohan_file", "daichang_file"]:
        fname = st.session_state.get(f"{key}:filename", "")
        used  = st.session_state.get(f"{key}:use", False)
        present = st.session_state.get(key) is not None
        parts.append(f"{key}:{present}:{used}:{fname}")
    return "|".join(parts)

# 在需要显示的地方调用它：签名一致就显示“统计完成”
def show_persistent_success():
    sig = _current_signature()
    if st.session_state.get("_last_success_sig") == sig:
        st.success("✅ 统计完成")




st.set_page_config(page_title="担保业务统计工具", layout="wide")

set_sidebar_width(360)   # ← 想多宽填多少，比如 320/360/400

page = render_status_sidebar()



# ===================== 工作日志 =====================
if page == "工作日志":




#         # def show_upload_summary():

#         #     # 先校验：筛选条件必须上传且参与统计（你那边已禁用为必选，这里再兜底）
#         #     if not st.session_state.get("filter_file"):
#         #         st.error("❌ 未上传【筛选条件.xlsx】；请先上传后再继续。")
#         #         return False
#         #     if not st.session_state.get("filter_file:use", True):
#         #         st.error("❌ 【筛选条件.xlsx】未被勾选参与统计。")
#         #         return False

#         #     # 四类业务：只看勾选状态（:use），未上传则不会有 :use，自然视为 False
#         #     use_map = {
#         #         "传统": st.session_state.get("trad_file:use", False),
#         #         "批量": st.session_state.get("batch_file:use", False),
#         #         "保函":     st.session_state.get("baohan_file:use", False),
#         #         "代偿": st.session_state.get("daichang_file:use", False),
#         #     }

#         #     any_checked = any(use_map.values())
#         #     all_checked = all(use_map.values())

#         #     if all_checked:
#         #         st.text("✅ 本次统计全部数据（传统、批量、保函、代偿）。")
#         #     elif any_checked:
#         #         not_used = [name for name, used in use_map.items() if not used]
#         #         st.text("本次不统计以下业务数据，相关指标显示为0：")
#         #         for name in not_used:
#         #             st.text(name)

#         #     return True
#         # _ = show_upload_summary()
# # ……（上面还是上传器那一段）……

# # 小工具：根据 :use 返回文件或 None
    def effective_file(key: str):
        return st.session_state.get(key) if st.session_state.get(f"{key}:use", False) else None

    # === 用侧边栏按钮发出的信号来触发执行 ===
# 报表页：仅在这次点击后运行一次

    if st.session_state.pop("_do_run", False):
        log_area = st.empty()          # 可选：把日志放在一个占位容器里
        with log_area.container():
                # ↓↓↓ 这里放你 4 段 st.status(...) 的全部代码 ↓↓↓
                # with st.status("读取保函…", ...): ...
                # with st.status("读取批量…", ...): ...
                # with st.status("读取传统…", ...): ...
                # with st.status("读取代偿…", ...): ...
                # ↑↑↑ 原样搬进来即可 ↑↑↑

            # 跑完写入成功签名（你已有的函数）
            

            # 先取勾选状态对应的“有效文件”
            filter_file   = effective_file("filter_file")   # 必选
            trad_file     = effective_file("trad_file")
            batch_file    = effective_file("batch_file")
            baohan_file   = effective_file("baohan_file")
            daichang_file = effective_file("daichang_file")

            # if filter_file is None:
            #     st.error("未上传【筛选条件】")
            #     st.stop()

            # if not (trad_file or batch_file or baohan_file or daichang_file):
            #     st.error("请至少勾选一类业务参与统计")
            #     st.stop()

            as_of = st.session_state.get("as_of", datetime.today())   # 基准日来自 sidebar
            as_of_dt = pd.to_datetime(as_of)

            # ← 这里保持你原来“执行统计”的整段逻辑（读取、calc_xxx、写入 session_state）
            #    例如：读取保函/批量/传统/代偿、calc_*、保存 *_res、*_overdue 等
            #    你可以直接把原先 if st.button(...): 里的内容粘贴进来

            with st.status("读取保函…", expanded=True, state="running", width=500) as status:     
                if baohan_file is None:
                    pass
                    status.update(label="无保函文件，相关指标显示为0", state="error", expanded=False)
                elif baohan_file:
                    def _load_baohan_inline(file_obj) -> pd.DataFrame:
                        xl = pd.ExcelFile(BytesIO(file_obj.getvalue()))
                        sheet = extractsheet_baohan(xl)

                        def _flatten_cols(multi_cols):
                            new_cols = []
                            for idx, col in enumerate(multi_cols):
                                parts = []
                                for piece in (col if isinstance(col, tuple) else (col,)):
                                    s = str(piece).strip()
                                    if (not s) or s.lower() == "nan" or s.startswith("Unnamed"):
                                        continue
                                    parts.append(s.replace("\u3000",""))  # 去全角空格
                                new_cols.append("_".join(parts) if parts else f"col_{idx}")
                            return new_cols

                        df = xl.parse(sheet_name=sheet, header=[2, 3])
                        df.columns = _flatten_cols(df.columns)
                        df = _clean_columns(df)
                        return df  # ← 关键：返回 DataFrame

                    df_baohan = _load_baohan_inline(baohan_file)
                    st.write(f"• 保函表已读取：{df_baohan.shape[0]} 行 × {df_baohan.shape[1]} 列")

                    st.write("• 统计保函指标…")
                    st.session_state["baohan_res"] = calc_baohan_metrics(df_baohan, as_of_dt)
                    status.update(label="保函统计完成", state="complete", expanded=False)
                def convert_new_batch_to_old_format(df: pd.DataFrame) -> pd.DataFrame:
                    # 定义新旧列名的映射关系
                    col_map = {
                        "放款日期": "主债权起始日期",
                        "放款到期日": "主债权到期日期",
                        "放款金额": "主债权金额",
                        "年化担保费率": "担保年费率",
                        "客户名称": "债务人名称",
                        "分险比例-放款机构": "分险比例(债权人)",    
                        "项目阶段": "是否已解保",
                        "业务状态": "备案状态",
                        "放款机构": "债权人名称",
                    }
                    # 只重命名存在的列
                    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
                    df = df.drop(columns=["责任余额"])
                    df["分险比例(直担)"] = 100-df["分险比例(债权人)"]
                    # 只保留新旧映射列和未修改的列，但只显示新旧映射列的前十行
                    cols_to_show = list(col_map.values())
                    df_show = df[cols_to_show].head(10)
                    # st.dataframe(df_show, use_container_width=True)
                    return df

            with st.status("读取批量…", expanded=True, state="running", width=500) as status: 
                if batch_file is None:
                    pass
                    status.update(label="无批量文件，相关指标显示为0", state="error", expanded=False)
                elif batch_file:
                    def load_batch_data(ledger_file, filter_file, *, header_row: int = 0) -> pd.DataFrame:
                        xl = pd.ExcelFile(BytesIO(ledger_file.getvalue()))
                        sheet = extractsheet(xl)

                        df_batch = xl.parse(sheet_name=sheet, header=header_row)

                        df_batch = _clean_columns(df_batch)

                        df_map = pd.read_excel(BytesIO(filter_file.getvalue()), sheet_name="业务分类")
                        df_map["业务品种"] = df_map["业务品种"].astype(str).str.strip()

                        df_batch["担保产品"] = df_batch["担保产品"].astype(str).str.strip()
                        # 合并所有 df_map 的列到 df_batch，避免丢失信息
                        df_batch = df_batch.merge(
                            df_map,
                            how="left",
                            left_on="担保产品",
                            right_on="业务品种",
                            suffixes=("", "_map"),
                        )
                        # 再次用“业务品种”合并，补充所有 df_map 列
                        df_batch = df_batch.merge(df_map, how="left", on="业务品种", suffixes=("", "_map2"))
                        if "业务品种2" in df_batch.columns:
                            df_batch = df_batch[df_batch["业务品种2"] == "批量"]
                        else:
                            st.warning("未找到 '业务品种2' 列，已跳过批量筛选。")

                        if "分险比例-放款机构" in df_batch.columns:
                            st.write("转换未备案的批量台账")
                            df_batch = convert_new_batch_to_old_format(df_batch)
                        else:
                            st.write("本次统计已备案的批量台账")
                        df_batch = df_batch.rename(columns={"在保余额": "名义在保余额"})
                        df_batch["责任余额"] = 0.01 * (
                            df_batch["分险比例(直担)"]
                            - df_batch["分险比例-国担"]
                            - df_batch["分险比例-市再担保"]
                            - df_batch["分险比例-省再担保"]
                            - df_batch["分险比例-其他"]
                        ) * df_batch["名义在保余额"]
                        df_batch["在保余额"] = (1 - 0.01 * df_batch["分险比例(债权人)"]) * df_batch["名义在保余额"]
                        df_batch["实际放款"] = (1 - 0.01 * df_batch["分险比例(债权人)"]) * df_batch["主债权金额"]

                        df_batch["担保费"] = df_batch["主债权金额"] * 0.01 * df_batch["担保年费率"]
                        df_batch["主债权起始日期"] = pd.to_datetime(df_batch["主债权起始日期"], errors="coerce")
                        df_batch["主债权到期日期"] = pd.to_datetime(df_batch["主债权到期日期"], errors="coerce")


                        return df_batch
                    def load_batch2_data(ledger_file, filter_file, *, header_row: int = 0) -> pd.DataFrame:
                        xl = pd.ExcelFile(BytesIO(ledger_file.getvalue()))
                        sheet = extractsheet_taizhang(xl)

                        df_batch2 = xl.parse(sheet_name=sheet, header=header_row)

                        df_batch2 = _clean_columns(df_batch2)

                        df_map = pd.read_excel(BytesIO(filter_file.getvalue()), sheet_name="业务分类")
                        df_map["业务品种"] = df_map["业务品种"].astype(str).str.strip()

                        df_batch2["担保产品"] = df_batch2["担保产品"].astype(str).str.strip()
                        # 合并所有 df_map 的列到 df_batch，避免丢失信息
                        df_batch2 = df_batch2.merge(
                            df_map,
                            how="left",
                            left_on="担保产品",
                            right_on="业务品种",
                            suffixes=("", "_map"),
                        )
                        # 再次用“业务品种”合并，补充所有 df_map 列
                        df_batch2 = df_batch2.merge(df_map, how="left", on="业务品种", suffixes=("", "_map2"))
                        if "分险比例-放款机构" in df_batch2.columns:
                            df_batch2 = convert_new_batch_to_old_format(df_batch2)
                        df_batch2 = df_batch2.rename(columns={"在保余额": "名义在保余额"})
                        df_batch2["责任余额"] = 0.01 * (
                            df_batch2["分险比例(直担)"]
                            - df_batch2["分险比例-国担"]
                            - df_batch2["分险比例-市再担保"]
                            - df_batch2["分险比例-省再担保"]
                            - df_batch2["分险比例-其他"]
                        ) * df_batch2["名义在保余额"]
                        df_batch2["在保余额"] = (1 - 0.01 * df_batch2["分险比例(债权人)"]) * df_batch2["名义在保余额"]
                        df_batch2["实际放款"] = (1 - 0.01 * df_batch2["分险比例(债权人)"]) * df_batch2["主债权金额"]

                        df_batch2["担保费"] = df_batch2["主债权金额"] * 0.01 * df_batch2["担保年费率"]
                        df_batch2["主债权起始日期"] = pd.to_datetime(df_batch2["主债权起始日期"], errors="coerce")
                        df_batch2["主债权到期日期"] = pd.to_datetime(df_batch2["主债权到期日期"], errors="coerce")


                        return df_batch2
                    
                    df_batch = load_batch_data(batch_file, filter_file)
                    df_batch2 = load_batch2_data(batch_file, filter_file)
                    
                    df_batch_overdue = df_batch[
                        (df_batch["主债权到期日期"].notna()) &
                        (df_batch["主债权到期日期"] < as_of_dt.normalize()) &
                        (df_batch["在保余额"] != 0)
                    ]
                    st.write("批量在保余额检查")
                    st.session_state["batch_overdue"] = df_batch_overdue
                    st.write("统计批量指标")
                    as_of_dt = pd.to_datetime(as_of)
                    st.session_state["batch_res"] = calc_batch_metrics(df_batch, as_of_dt)
                    status.update(label="批量统计完成", state="complete", expanded=False)
            with st.status("读取传统…", expanded=True, state="running", width=500) as status:
                if trad_file is None:
                    pass
                    status.update(label="无传统文件，相关指标显示为0", state="error", expanded=False)
                if trad_file:
                    def load_trad_data(ledger_file, filter_file, *, header_row: int = 2) -> pd.DataFrame:
                        xl = pd.ExcelFile(BytesIO(ledger_file.getvalue()))
                        sheet = extractsheet_taizhang(xl)

                        df_taizhang = xl.parse(sheet_name=sheet, header=header_row)
                        df_taizhang = _clean_columns(df_taizhang)

                        df_map = pd.read_excel(BytesIO(filter_file.getvalue()), sheet_name="业务分类")
                        gov_list = (
                            pd.read_excel(BytesIO(filter_file.getvalue()), sheet_name="国企名单", usecols=["客户名称"])
                            .iloc[:, 0]
                            .astype(str)
                            .str.strip()
                            .tolist()
                        )

                        df_taizhang["客户名称"] = df_taizhang["客户名称"].astype(str).str.strip()
                        df_taizhang["业务品种"] = df_taizhang["业务品种"].astype(str).str.strip()
                        df_taizhang["国企民企"] = np.where(
                            df_taizhang["客户名称"].isin(gov_list) | (df_taizhang["业务品种"] == "委托贷款"),
                            "国企",
                            "民企",
                        )
                        df_taizhang = df_taizhang.merge(df_map, how="left", on="业务品种")
                        df_taizhang = df_taizhang[df_taizhang["业务品种2"] == "传统"]
                        df_taizhang = df_taizhang.rename(columns={"在保余额": "名义在保余额"})
                        df_taizhang["在保余额"] = (1 - df_taizhang["银行"]) * df_taizhang["名义在保余额"]

                        df_taizhang["实际放款"] = (1 - df_taizhang["银行"]) * df_taizhang["放款金额"]
                        df_taizhang["放款时间"] = pd.to_datetime(df_taizhang["放款时间"], errors="coerce")
                        df_taizhang["实际到期时间"] = pd.to_datetime(df_taizhang["实际到期时间"], errors="coerce")
                        return df_taizhang                
                    df_trad = load_trad_data(trad_file, filter_file)

                    #st.write("df_baohan 列：", list(df_baohan.columns))
                    #check
                    #st.dataframe(df_baohan.head(10), use_container_width=True)
                    #check
                    # #st.dataframe(df_daichang.head(10), use_container_width=True)
                    st.write(f"• 传统表已读取：{df_trad.shape[0]} 行 × {df_trad.shape[1]} 列")
                    df_trad_overdue = df_trad[
                        (df_trad["实际到期时间"].notna()) &
                        (df_trad["实际到期时间"] < as_of_dt.normalize()) &
                        (df_trad["在保余额"] != 0)
                    ]
                    st.session_state["trad_overdue"] = df_trad_overdue
                    st.write("传统在保余额检查...")
                    st.session_state["trad_res"] = calc_trad_metrics(df_trad, as_of_dt)
                    status.update(label="传统统计完成", state="complete", expanded=False)
            with st.status("读取代偿…", expanded=True, state="running", width=500) as status:
                if daichang_file is None:
                    pass
                    status.update(label="无代偿文件，相关指标显示为0", state="error", expanded=False)
                if daichang_file and batch_file:
                    def load_daichang_data(daichang_file, df_batch2) -> pd.DataFrame:
                        xl = pd.ExcelFile(BytesIO(daichang_file.getvalue()))
                        sheet = extractsheet_daichang(xl)

                        df_daichang = xl.parse(sheet_name=sheet, header=4)
                        df_daichang = _clean_columns(df_daichang)
                        df_daichang["代偿时间"] = pd.to_datetime(df_daichang["代偿时间"], errors="coerce")
                        df_daichang["代偿金额"] = pd.to_numeric(df_daichang["代偿金额"], errors="coerce").fillna(0) / 10000
                        df_daichang["担保金额"] = pd.to_numeric(df_daichang["担保金额"], errors="coerce").fillna(0) / 10000

                        # Drop rows where 贷款银行 is null or empty
                        df_daichang = df_daichang[df_daichang["贷款银行"].notna() & (df_daichang["贷款银行"].astype(str).str.strip() != "")]
                        # 新增“政策扶持领域”列，默认空
                        # 新增“政策扶持领域”列，默认空，并放在最左侧
                        df_daichang.insert(0, "政策扶持领域", "")
                        st.write("在批量台账中找到代偿债务人名称，识别政策扶持领域...")
                        # 遍历 df_daichang，每行根据“企业名称”和“担保金额”在 df_batch 查找匹配
                        for idx, row in df_daichang.iterrows():
                            # 如果企业名称有顿号，新增一列“企业名称_首”，为顿号之前的名字
                            if "企业名称_首" not in df_batch2.columns:
                                df_batch2["企业名称_首"] = df_batch2["债务人名称"].astype(str).str.split("、").str[0]
                            # 当前行企业名称也取顿号前部分
                            row_name_first = str(row["企业名称"]).split("、")[0]
                            mask = (
                                (df_batch2["企业名称_首"] == row_name_first) &
                                (np.isclose(df_batch2["主债权金额"], row["担保金额"], atol=0.01))
                            )
                            matched = df_batch2[mask]
                            if not matched.empty:
                                # 取第一条匹配的“政策扶持领域”
                                # 如果有多条匹配，合并所有匹配的相关字段为一张表并展示
                                if len(matched) > 1:
                                    st.dataframe(matched[["业务编号","担保产品","政策扶持领域","债务人名称","债务人证件号码", "主债权金额", "主债权到期日期",  "债权人名称", "备案状态"]], use_container_width=True)
                                df_daichang.at[idx, "政策扶持领域"] = matched.iloc[0]["政策扶持领域"]
                        # 删除原处 st.success/st.dataframe 代码

                        # 在 if page == "工作日志": 页面，统计完成后展示 df_daichang
                        # 找到 if st.button("🚀 执行统计", use_container_width=True): 代码块
                        # 在 st.success("✅ 统计完成！下方可直接查看统计结果") 之后添加：
                        
                        
                        
                        return df_daichang 
                    df_daichang = load_daichang_data(daichang_file, df_batch2)      
                    st.session_state["df_daichang"] = df_daichang
                    st.write(f"• 代偿表已读取：{df_daichang.shape[0]} 行 × {df_daichang.shape[1]} 列")
                    st.write("统计代偿指标…")
                    st.session_state["daichang_res"] = calc_daichang_metrics(df_daichang, as_of_dt)
                    status.update(label="代偿统计完成", state="complete", expanded=False)
        st.session_state["_last_success_sig"] = _current_signature()
    for key, title, fname in [
        ("trad_res", "📈 传统台账统计结果", "传统统计"),
        ("batch_res", "📈 批量业务统计结果", "批量统计"),
        ("baohan_res", "📈 保函业务统计结果", "保函统计"),
        ("daichang_res", "📈 代偿业务统计结果", "代偿统计"),
        ("df_daichang", "📈 代偿&批量合并", "代偿合并后表"),

    ]:
        if key in st.session_state:
            # 不展示/导出 df_daichang
            if key != "df_daichang":
                st.subheader(title)
                ser = st.session_state[key]
                out = BytesIO()
                ser.rename_axis("指标").reset_index().to_excel(out, index=False)
                st.download_button(
                    f"💾 下载{title.replace('📈 ', '').replace('统计结果', '')}结果",
                    data=out.getvalue(),
                    file_name=f"{fname}_{datetime.today():%Y%m%d}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
                st.dataframe(ser.to_frame("数值"))
            else:
                st.subheader(title)
                df = st.session_state[key]
                out = BytesIO()
                df.to_excel(out, index=False)
                st.download_button(
                    "💾 下载代偿&批量合并结果",
                    data=out.getvalue(),
                    file_name=f"代偿批量合并_{datetime.today():%Y%m%d}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )
                st.dataframe(df, use_container_width=True)
# ===================== 报表 =====================
elif page == "报表":

    # filter_file = st.session_state.get("filter_file", None)
    # # trad_file = st.session_state.get("trad_file", None)
    # # batch_file = st.session_state.get("batch_file", None)
    # # baohan_file = st.session_state.get("baohan_file", None)
    # # daichang_file = st.session_state.get("daichang_file", None)
    # if filter_file is None:
    #     st.warning("⚠️ 未找到【筛选条件】缓存，请回到第一页上传。")
    #     st.stop()

    # # ……照常处理


    # ① 把所有统计结果汇总进 all_res -------------------------
    patterns = ["_名义放款", "_当年_名义放款"]
    all_res = {}
    for key in ["trad_res", "batch_res", "baohan_res", "daichang_res"]:
        if key in st.session_state:
            all_res.update(st.session_state[key])
    # 用于判断是否“空”的最小 DataFrame
    rows = []
    for pat in patterns:
        rows.extend([{"指标": k, "数值": v, "分组": pat}
                     for k, v in all_res.items() if pat in k])
    df = pd.DataFrame(rows)
    # ---------------------------------------------------------
    st.title("📊 分类汇总")
    st.text(
        "名义在保余额 > 在保余额（扣除银行分险） > 责任余额（扣除银行分险和再担保）\n"
        "名义放款 > 实际放款（扣除银行分险）\n"
        "广义小微：小型企业、微型企业、小微企业主、个体工商户\n"
        "担保费：不统计已经解保的"
    )
    col_left, col_right = st.columns([1, 3])
    with col_left:
        st.text("（可选）\n输入以前的数据，按回车，计算解保额")
    with col_right:
        input_fields = [
            ("上月_在保_在保余额", "上月在保余额（万元）"),
            ("上一年_在保_在保余额", "上一年在保余额（万元）"),
            ("上一年_在保_责任余额", "上一年在保责任余额（万元）"),
        ]
        for key, label in input_fields:
            val = st.number_input(label, min_value=0.0, value=0.0, step=0.01, format="%.2f")
            st.session_state[key] = val
            all_res[key] = val



    # ② 两组公式规则 -----------------------------------------
    rules_city = [
        "本年累计发生金额（扣除银行分险）=批量_当年_实际放款+传统_当年_实际放款",
        "本年累计发生金额（扣除银行分险）同比增减=批量_当年_实际放款-批量_上一年_实际放款+传统_当年_实际放款-传统_上一年_实际放款",
        "在保余额=批量_在保_在保余额+传统_在保_在保余额",
        "同比增减=在保余额-上月_在保_在保余额",
        "比年初增减额=在保余额-上一年_在保_在保余额",
        "累计代偿=代偿_代偿金额",
        "本年累计代偿=代偿_当年_代偿金额",
        "本年累计担保户数=批量_当年_户数+传统_当年_户数",
        "本年累计担保户数同比增减=批量_当年_户数-批量_上一年_户数+传统_当年_户数-传统_上一年_户数",
        "在保企业客户数量=批量_在保_企业_户数+传统_在保_户数",
        "在保个人客户数量=批量_在保_个人_户数+传统_个体工商户及小微企业主_在保_户数",
        "正常类担保余额=批量_正常_名义在保余额+传统_正常_在保余额",
        "关注类担保余额=批量_关注_名义在保余额+传统_关注_在保余额",
        "次级类担保余额=批量_次级_名义在保余额+传统_次级_在保余额",
        "可疑类担保余额=批量_可疑_名义在保余额+传统_可疑_在保余额",
        "损失类担保余额=批量_损失_名义在保余额+传统_损失_在保余额",
    ]

    rules_cd_fin = [
        "实际在保余额=批量_在保_责任余额+传统_在保_责任余额",
        "较年初增减=实际在保余额-上一年_在保_责任余额",
        "客户数=批量_在保_户数+传统_在保_户数",
        "1.非农小微企业在保余额=批量_在保_非农小微_在保余额+传统_在保_小微_在保余额",
        "1.非农小微企业客户数=批量_在保_非农小微_户数+传统_在保_小微_户数",
        "2.农业小微企业在保余额=批量_在保_农业小微_在保余额",
        "2.农业小微企业客户数=批量_在保_农业小微_户数",
        "3.城镇居民（含个体工商户）在保余额=批量_城镇居民_在保_在保余额",
        "3.城镇居民（含个体工商户）客户数=批量_城镇居民_在保_户数",
        "4.农村居民（含个体工商户）在保余额=批量_农户_在保_在保余额",
        "4.农村居民（含个体工商户）客户数=批量_农户_在保_户数",
        "批量_不良_名义在保余额=批量_次级_名义在保余额-批量_可疑_名义在保余额-批量_损失_名义在保余额",
        "传统_不良_在保余额=传统_次级_在保余额-传统_可疑_在保余额-传统_损失_在保余额",
        "不良融资担保余额=批量_不良_名义在保余额+传统_不良_在保余额"
    ]

    rules_city_yoy = [
        "本年累计担保金额=批量_当年_实际放款+传统_当年_实际放款",
        "本年累计担保金额同比增减=批量_当年_实际放款-批量_上一年_实际放款+传统_当年_实际放款-传统_上一年_实际放款",
        "在保余额=批量_在保_在保余额+传统_在保_在保余额",
        "同比增减额=在保余额-上月_在保_在保余额",
        "比年初增减额=在保余额-上一年_在保_在保余额",
        "累计代偿=代偿_代偿金额",
        "本年累计代偿=代偿_当年_代偿金额",
        "本年累计担保户数=批量_当年_户数+传统_当年_户数",
        "本年累计担保户数同比增减=批量_当年_户数-批量_上一年_户数+传统_当年_户数-传统_上一年_户数",
        "在保企业客户数量=批量_在保_企业_户数+传统_在保_户数",
        "在保个人客户数量=批量_在保_个人_户数+传统_个体工商户及小微企业主_在保_户数",
        "最大单一客户在保余额=传统_单户责任最大_责任余额",
        "前十大客户在保余额=传统_单户责任前10_责任余额",
        "正常类担保余额=批量_正常_名义在保余额+传统_正常_在保余额",
        "关注类担保余额=批量_关注_名义在保余额+传统_关注_在保余额",
        "次级类担保余额=批量_次级_名义在保余额+传统_次级_在保余额",
        "可疑类担保余额=批量_可疑_名义在保余额+传统_可疑_在保余额",
        "损失类担保余额=批量_损失_名义在保余额+传统_损失_在保余额",
        "非融本年累计担保金额=保函_当年_放款金额",
        "非融在保余额=保函_在保_在保余额",
        "非融本年累计代偿=保函_当年_代偿金额",
        "非融本年累计损失=保函_当年_损失",
    ]

    rules_prov = [
        "中小企业借款类担保业务当年累计发生额（万元）=批量_中小_当年_实际放款+传统_中小_当年_实际放款",
        "其中：小微企业当年累计发生额（万元）=批量_小微_当年_实际放款+传统_小微_当年_实际放款",
        "中小企业借款类担保业务当年累计发生户数=批量_中小_当年_户数+传统_中小_当年_户数",
        
        "其中：小微企业当年累计发生户数=批量_小微_当年_户数+传统_小微_当年_户数",
        "中小企业借款类担保业务当年累计发生笔数 =批量_中小_当年_笔数+传统_中小_当年_笔数",
        "其中：小微企业当年累计发生笔数=批量_小微_当年_笔数+传统_小微_当年_笔数",
        "中小企业借款类在保余额=批量_中小_在保_在保余额+传统_中小_在保_在保余额",
        "其中：小微企业在保余额=批量_小微_在保_在保余额+传统_小微_在保_在保余额",
        "中小企业借款类代偿当年累计发生额（万元）=代偿_当年_小微_代偿金额",
        "其中：小微企业代偿当年累计发生额（万元）=代偿_当年_小微_代偿金额",
        "个体工商户、小微企业主、新型农业经营主体担保业务当年累计发生额（不含创业小额贷款担保业务）=批量_个体工商户及小微企业主_实际放款+批量_农户及新型农业经营主体_实际放款+传统_个体工商户及小微企业主_实际放款+传统_农户及新型农业经营主体_实际放款",
        "个体工商户、小微企业主、新型农业经营主体担保业务在保余额（不含创业小额贷款担保业务）=批量_个体工商户及小微企业主_在保_在保余额+批量_农户及新型农业经营主体_在保_在保余额+传统_个体工商户及小微企业主_在保_在保余额+传统_农户及新型农业经营主体_在保余额",
    ]
    rules_resp = [
        "单户金额500万及以下“三农”类在保余额（实际余额）=批量_三农_单户在保<=500_责任余额+传统_三农_单户在保<=500_责任余额",
        "其中：单户在保余额200万人民币及以下的农户借款类担保在保余额（实际余额）=批量_农户_单户在保<=200_责任余额",
        "单户担保金额500万元人民币及以下的小微企业借款类担保余额（实际余额）=批量_小微_单户在保<=500_责任余额+传统_小微_单户在保<=500_责任余额",
        "单户担保金额500万元人民币及以下的小微企业借款类_其中：费率=单户担保金额500万元人民币及以下的小微企业借款类_在保_担保费/单户担保金额500万元人民币及以下的小微企业借款类_在保_名义放款",
        "其他借款类在保余额（实际余额）= 在保_责任余额-单户担保金额500万元人民币及以下的小微企业借款类担保余额（实际余额）",
        "其他借款类_其中：费率=其他借款类_在保_担保费/其他借款类_在保_名义放款",
        "本月解保额=上月_在保_在保余额+当月_实际放款-在保_在保余额",
        "本年累计解保=上一年_在保_在保余额+当年_实际放款-当年_在保_在保余额"
    ]


    # 额外自定义指标，可以直接赋值，不通过公式计算
    # 额外自定义指标，可以直接赋值，不通过公式计算
    custom_values = {
        "批量_科创_当年代偿_代偿金额": 0,
        "批量_关注_名义在保余额": 280,
        "批量_次级_名义在保余额": 30,
        "批量_可疑_名义在保余额": 0,
        "批量_损失_名义在保余额": 0,
        "保函_当年_代偿金额": 0,
        "保函_当年_损失": 0,
    }

    rules_supp = [
        "批量_正常_名义在保余额=批量_在保_名义在保余额-批量_关注_名义在保余额-批量_次级_名义在保余额-批量_可疑_名义在保余额-批量_损失_名义在保余额",
        "当月_实际放款=批量_当月_实际放款+传统_当月_实际放款",
        "在保_在保余额=批量_在保_在保余额+传统_在保_在保余额",
        "在保_责任余额=批量_在保_责任余额+传统_在保_责任余额",
        "当年_实际放款=批量_当年_实际放款+传统_当年_实际放款",
        "在保_担保费=传统_在保_担保费+批量_在保_担保费",
        "在保_名义放款=传统_在保_名义放款+批量_在保_名义放款",
        "单户担保金额500万元人民币及以下的小微企业借款类_在保_担保费=批量_小微_单户在保<=500_在保_担保费+传统_小微_单户在保<=500_在保_担保费",
        "单户担保金额500万元人民币及以下的小微企业借款类_在保_名义放款=批量_小微_单户在保<=500_在保_名义放款+传统_小微_单户在保<=500_在保_名义放款",
        "其他借款类_在保_担保费=在保_担保费-单户担保金额500万元人民币及以下的小微企业借款类_在保_担保费",
        "其他借款类_在保_名义放款=在保_名义放款-单户担保金额500万元人民币及以下的小微企业借款类_在保_名义放款",
    ]


    rules_sur = [
      #  "三、当年融资担保业务"
        "当年累计增加发生额=批量_当年_实际放款+传统_当年_实际放款",
        "当年累计增加发生额（名义）=批量_当年_名义放款+传统_当年_名义放款",
        "当年累计发生客户数=批量_当年_户数+传统_当年_户数",

      #  "四、科创企业专项统计",
        "本年度科创企业累计担保发生额=批量_当年_科创_实际放款",
        "本年度科创企业累计担保发生户数=批量_当年_科创_户数",
        "本年度科创业务担保余额=批量_科创_在保_在保余额",
        "本年度科创业务在保户数=批量_科创_在保_户数",
        "本年度科创企业累计代偿金额=批量_科创_当年代偿_代偿金额",

      #  "五、支农支小专项统计（二者满足其一即统计）"
        "本年度新增支农支小业务累计发生额（名义）=批量_当年_支农支小_名义放款+传统_当年_支农支小_名义放款",
        "本年度新增支农支小业务累计发生额（实际）=批量_当年_支农支小_实际放款+传统_当年_支农支小_实际放款",
        "本年度新增支农支小户数=批量_当年_支农支小_户数+传统_当年_支农支小_户数",

      #  "六、民营企业专项统计（涵盖所有非国有制经营主体个人+企业）"
        "本年度新增民营企业累计发生额（名义）=批量_当年_民企_名义放款+传统_当年_民企_名义放款",
        "本年度新增民营企业累计发生额（实际）=批量_当年_民企_实际放款+传统_当年_民企_实际放款",
        "本年度新增民企户数=批量_当年_民企_户数+传统_当年_民企_户数",

       # "七、融资性担保在保余额"
        "名义在保余额=批量_在保_名义在保余额+传统_在保_名义在保余额",
        "银行分险金额=批量_在保_名义在保余额-批量_在保_在保余额+传统_在保_名义在保余额-传统_在保_在保余额",
        "再担保分险金额=批量_在保_在保余额-批量_在保_责任余额+传统_在保_在保余额-传统_在保_责任余额",
        "客户数=批量_在保_户数+传统_在保_户数",
        "担保费率低于1%(含)的担保余额=批量_担保费率低于1%(含)_在保_在保余额+传统_担保费率低于1%(含)_在保_在保余额",
        "1.小微企业余额（含小型企业、微型企业、个体工商户以及小微企业主）=批量_广义小微_在保_在保余额+传统_广义小微_在保_在保余额",
        "2.小微企业户数（含小型企业、微型企业、个体工商户以及小微企业主）=批量_广义小微_在保_户数+传统_广义小微_在保_户数",
        "其中：个体工商户及小微企业主余额=批量_个体工商户及小微企业主_在保_在保余额+传统_个体工商户及小微企业主_在保_在保余额",
        "其中：个体工商户及小微企业主户数=批量_个体工商户及小微企业主_在保_户数+传统_个体工商户及小微企业主_在保_户数",
        "2.农户及新型农业经营主体余额=批量_农户_在保_在保余额",
        "2.农户及新型农业经营主体户数=批量_农户_在保_户数",
        "3.支农支小（剔重）余额=批量_支农支小_在保_在保余额+传统_支农支小_在保_在保余额",
        "3.支农支小（剔重）户数=批量_支农支小_在保_户数+传统_支农支小_在保_户数",
        "首贷余额=批量_首贷户_在保_在保余额",
        "首贷户数=批量_首贷户_在保_户数",



       # "八、非融资性担保余额"
       "非融资性担保余额=保函_在保_在保余额",

    ]



    # ③ 通用函数：把公式列表转成可展示的 DataFrame -------------


    def build_formula_df(rule_list, res_dict):
        rows, max_len = [], 0
        num_pat = re.compile(r'^[+-]?\d+(?:\.\d+)?$')

        def as_value(token: str):
            """把 token 解析成数值：先查 res_dict，再尝试数字常量，否则 0。"""
            if token in res_dict:
                return res_dict[token]
            if num_pat.match(token):
                return float(token)
            return 0.0

        for f in rule_list:
            m = re.match(r'\s*(.+?)\s*=\s*(.+)', f)
            if not m:
                continue
            target, expr = m.group(1).strip(), m.group(2).strip()

            # 1) 令牌化：支持 + - * /
            tokens = [t.strip() for t in re.split(r'([+\-*/])', expr) if t and t.strip()]
            ops, operands = [], []

            # 2) 处理前缀一元 +/-（* 和 / 不作为一元）
            i = 0
            pending_unary = '+'
            if tokens and tokens[0] in ('+', '-'):
                pending_unary = tokens[0]
                i = 1

            # 3) 解析为：operand (op operand)*
            if i >= len(tokens):
                continue
            operands.append(tokens[i]); i += 1
            while i < len(tokens):
                op = tokens[i]
                if op not in ('+', '-', '*', '/'):
                    # 容错：两个操作数相邻，当作漏了 '+'
                    ops.append('+')
                    operands.append(op)
                    i += 1
                    continue
                ops.append(op)
                if i + 1 < len(tokens):
                    operands.append(tokens[i + 1])
                    i += 2
                else:
                    # 末尾缺少操作数则丢弃该操作符
                    i += 1

            # 4) 计算（支持运算优先级：先乘除后加减）
            values = [as_value(k) for k in operands]
            if not values:
                continue

            # current_term 累乘/除的“项”；current_add 保存该项应以 + 还是 - 加入 total
            current_term = values[0]
            current_add = '+' if pending_unary == '+' else '-'
            total = None

            for idx, op in enumerate(ops, start=1):
                v = values[idx] if idx < len(values) else 0.0
                if op == '*':
                    current_term = current_term * v
                elif op == '/':
                    current_term = (current_term / v) if v != 0 else 0.0
                elif op in ('+', '-'):
                    # 先把上一项结算进 total
                    if total is None:
                        total = current_term if current_add == '+' else -current_term
                    else:
                        total = total + current_term if current_add == '+' else total - current_term
                    # 开启新项
                    current_term = v
                    current_add = op

            # 循环结束，收尾结算最后一项
            if total is None:
                total = current_term if current_add == '+' else -current_term
            else:
                total = total + current_term if current_add == '+' else total - current_term

            # 5) 展示：首列放 target/total；每个操作数根据符号加 Emoji 前缀
            items = [target]
            vals = [total]

            op_signs = [pending_unary] + ops  # 与 operands 对齐的“符号列表”
            for k, sign in zip(operands, op_signs):
                label = k
                if sign == '-':
                    label = f"（➖）{k}"
                elif sign == '/':
                    label = f"（➗）{k}"
                # 乘号和加号按你的要求保持原样（不加标记）
                items.append(label)
                vals.append(as_value(k))

            # 展平成一行："指标 值 指标 值 …"
            out_row = []
            for k, v in zip(items, vals):
                out_row.extend([k, v])

            max_len = max(max_len, len(out_row))
            rows.append(out_row)

            # 6) 写回计算结果，供后续规则引用
            res_dict[target] = total

        cols = [str(i + 1) for i in range(max_len)]
        padded = [r + [None] * (max_len - len(r)) for r in rows]
        return pd.DataFrame(padded, columns=cols)


    # ---------------------------------------------------------

    if not df.empty:
        left_col, right_col = st.columns([1, 4])
        with left_col:
            st.text("直接赋值的数据:")
        with right_col:
            st.text("、".join([f"{k}: {v}" for k, v in custom_values.items()]))
        all_res.update(custom_values)

        # 定义一个临时变量存放每一步的 DataFrame
        calc_steps = [
            ("辅助计算", rules_supp),
            ("市州（辖内）融资性担保机构经营月报表（填写版）", rules_city),
            ("市州（辖内）融资性担保机构经营月报表（同比数据）", rules_city_yoy),
            ("月度担保责任余额统计表（填写版）", rules_resp),
            ("成都市金融办融资性担保公司月度统计表（填写版）", rules_cd_fin),
            ("四川省融资担保机构月报数据统计表", rules_prov),
            ("省监管系统--月度经营情况表", rules_sur),
        ]
        def update_from_formula_df(all_res: dict, df_tmp: pd.DataFrame) -> None:
            # 只取“1”为指标、“2”为数值这两列
            col_key, col_val = "1", "2"
            if col_key not in df_tmp.columns or col_val not in df_tmp.columns:
                return
            sub = df_tmp[[col_key, col_val]].dropna(subset=[col_key]).copy()
            # 转成字典；把 None/NaN 转 0，确保是标量数字
            to_add = {}
            for k, v in zip(sub[col_key], sub[col_val]):
                key = str(k).strip()
                if key == "":
                    continue
                try:
                    val = float(v) if pd.notna(v) else 0.0
                except Exception:
                    # 非数字一律置 0，避免 object 混入
                    val = 0.0
                to_add[key] = val
            all_res.update(to_add)

        for title, rules in calc_steps:
            st.subheader(title)
            df_tmp = build_formula_df(rules, all_res)
            st.dataframe(df_tmp, use_container_width=True)
            update_from_formula_df(all_res, df_tmp)   # ← 只合并 target/total



        st.subheader("全部结果")
        final_df = (
            pd.Series(all_res, name="数值")
            .reset_index().rename(columns={"index": "指标"})
        )
        final_df["数值"] = pd.to_numeric(final_df["数值"], errors="coerce").fillna(0.0)
        st.dataframe(final_df, use_container_width=True)
        st.session_state["final_all_res"] = dict(zip(final_df["指标"], final_df["数值"]))


# ===================== 在保余额检查 =====================
elif page == "在保余额检查":
    st.title("⏰ 在保余额检查")

    if "trad_overdue" not in st.session_state:
        st.warning("未上传批量或传统台账文件")
        st.stop()

    df_trad_overdue = st.session_state["trad_overdue"].copy()
    trad_cols = df_trad_overdue.columns.tolist()
    trad_first = ["在保余额", "实际到期时间"]
    trad_cols = trad_first + [c for c in trad_cols if c not in trad_first]
    df_trad_overdue = df_trad_overdue[trad_cols]

    df_batch_overdue = st.session_state.get("batch_overdue", pd.DataFrame()).copy()
    if not df_batch_overdue.empty:
        batch_cols = df_batch_overdue.columns.tolist()
        batch_first = ["在保余额", "主债权到期日期"]
        batch_cols = batch_first + [c for c in batch_cols if c not in batch_first]
        df_batch_overdue = df_batch_overdue[batch_cols]

    st.subheader("传统台账到期未清零明细")
    if df_trad_overdue.empty:
        st.success("🎉 传统台账没有发现到期未清零记录，一切正常！")
    else:
        st.info(f"共有 **{len(df_trad_overdue)}** 行传统台账到期在保余额未清零：")
        st.dataframe(df_trad_overdue, use_container_width=True)
        out_trad = BytesIO()
        df_trad_overdue.to_excel(out_trad, index=False)
        st.download_button(
            "💾 下载传统台账在保余额明细 Excel",
            data=out_trad.getvalue(),
            file_name=f"传统台账在保余额未清零_{datetime.today():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )

    st.subheader("批量台账到期未清零明细")
    if df_batch_overdue.empty:
        st.success("🎉 批量台账没有发现到期未清零记录，一切正常！")
    else:
        st.info(f"共有 **{len(df_batch_overdue)}** 行批量台账到期在保余额未清零：")
        st.dataframe(df_batch_overdue, use_container_width=True)
        out_batch = BytesIO()
        df_batch_overdue.to_excel(out_batch, index=False)
        st.download_button(
            "💾 下载批量台账在保余额明细 Excel",
            data=out_batch.getvalue(),
            file_name=f"批量台账在保余额未清零_{datetime.today():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
