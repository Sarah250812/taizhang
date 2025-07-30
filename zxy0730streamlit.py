# app.py  ── 完整版：双页切换 + 完整计算逻辑
import streamlit as st
import pandas as pd, numpy as np
from datetime import datetime
from functools import reduce
from io import BytesIO

# ────────────────────────────
# ① 公共函数（与你的上一版完全一致）
# ────────────────────────────
def guess_sheet_name(xl: pd.ExcelFile) -> str:
    for name in xl.sheet_names:
        if "台账" in name or "总台账" in name:
            return name
    return xl.sheet_names[0]

def load_data(ledger_file, filter_file) -> pd.DataFrame:
    xl = pd.ExcelFile(ledger_file)
    sheet = guess_sheet_name(xl)
    st.info(f"📄 自动识别工作表：**{sheet}**")
    df = xl.parse(sheet_name=sheet, header=2)

    df_map = pd.read_excel(filter_file, sheet_name="业务分类")
    gov_list = (pd.read_excel(filter_file, sheet_name="国企名单", usecols=["客户名称"])
                  .iloc[:, 0].astype(str).str.strip().tolist())

    df["客户名称"] = df["客户名称"].astype(str).str.strip()
    df["业务品种"] = df["业务品种"].astype(str).str.strip()
    df["国企民企"] = np.where(
        df["客户名称"].isin(gov_list) | (df["业务品种"] == "委托贷款"), "国企", "民企"
    )
    df = df.merge(df_map, how="left", on="业务品种")

    df.columns = (df.columns
                    .str.replace(r"\s+", "", regex=True)
                    .str.replace(r"[（(]\s*(?:万元|%)\s*[）)]", "", regex=True))
    df["实际放款"] = df["放款金额"] - df["待放款金额"]
    df["放款时间"]   = pd.to_datetime(df["放款时间"],   errors="coerce")
    df["实际到期时间"] = pd.to_datetime(df["实际到期时间"], errors="coerce")
    return df

def calc_metrics(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    year_start  = as_of.replace(month=1,  day=1)
    year_end    = as_of.replace(month=12, day=31)
    month_start = as_of.replace(day=1)
    month_end   = (month_start + pd.offsets.MonthEnd(0))

    RULES = {
        "当年":  lambda d: d["放款时间"].between(year_start,  year_end)  & (d["放款金额"] > 0),
        "当月":  lambda d: d["放款时间"].between(month_start, month_end) & (d["放款金额"] > 0),
        "本月解保": lambda d: d["实际到期时间"].between(month_start, month_end),
        "本年解保": lambda d: d["实际到期时间"].between(year_start,  year_end),
        "在保":  lambda d: d["在保余额"] > 0,
        "传统":  lambda d: d["业务品种2"].isin(["传统"]),
        "全担":  lambda d: d["公司责任风险比例"] == "100%",
        "惠蓉贷": lambda d: d["业务品种3"] == "惠蓉贷",
        "驿享贷": lambda d: d["业务品种"]  == "驿享贷",
        "担保费率低于1%（含）": lambda d: d["担保费率/利率"] <= 1,
        "小微":  lambda d: d["企业类别"].isin(["小型","微型"]),
        "中型":  lambda d: d["企业类别"] == "中型",
        "中小":  lambda d: d["企业类别"].isin(["小型","微型","中型"]),
        "支农支小": lambda d: d["企业类别"].isin(["小型","微型","三农"]),
        "传统个体工商户及小微企业主": lambda d: d["业务品种"] == "惠抵贷",
        "农户及新型农业经营主体":     lambda d: d["企业类别"].isin(["三农"]),
        "新增":  lambda d: d["新增/续贷"] == "新增",
        "民企":  lambda d: d["国企民企"] == "民企",
        "国企":  lambda d: d["国企民企"] == "国企",
    }
    RULES.update({lvl: (lambda d, _lvl=lvl: d["风险等级"] == _lvl)
                  for lvl in ["正常","关注","次级","可疑","损失"]})

    AGG_MAP = {
        "名义放款": ("放款金额", "sum"),
        "实际放款": ("实际放款", "sum"),
        "在保余额": ("在保余额", "sum"),
        "笔数":     (None,       "count"),
        "户数":     ("客户名称", "nunique"),
    }

    def calc_metric(name: str):
        *rule_keys, agg_key = name.split("_")
        mask = reduce(lambda a,b: a & b,
                      [RULES[k](df) for k in rule_keys] or [pd.Series(True, index=df.index)])
        col, how = AGG_MAP[agg_key]
        if how == "sum":
            return df.loc[mask, col].sum()
        if how == "count":
            return int(mask.sum())
        if how == "nunique":
            return df.loc[mask, col].nunique()

    指标列表 = [
    "传统_当年_名义放款", "传统_当年_中型_名义放款", "传统_当年_小微_名义放款",
        "传统_当年_户数", "传统_当年_小微_户数", "传统_当年_笔数", "传统_当年_小微_笔数",
        "传统_中小_在保余额", "传统_中型_在保余额", "传统_当年_实际放款",
        "新增_传统_当年_支农支小_名义放款", "新增_传统_当年_支农支小_全担_名义放款",
        "新增_传统_当年_支农支小_惠蓉贷_名义放款", "新增_传统_当年_支农支小_户数",
        "传统_当年_支农支小_名义放款", "传统_当年_支农支小_全担_名义放款", "传统_当年_支农支小_惠蓉贷_名义放款",
        "传统_当年_支农支小_户数", "新增_传统_当年_民企_名义放款", "新增_传统_当年_民企_实际放款", "新增_传统_当年_民企_户数",
        "传统_当年_民企_名义放款", "传统_当年_民企_实际放款", "传统_当年_民企_户数",
        "传统_在保余额", "传统_小微_在保余额", "传统_在保_户数", "传统_小微_在保_户数",
        "传统_传统个体工商户及小微企业主_在保余额", "传统_传统个体工商户及小微企业主_在保_户数",
        "传统_农户及新型农业经营主体_在保余额", "传统_农户及新型农业经营主体_在保_户数",
        "传统_支农支小_在保余额", "传统_支农支小_在保_户数",
        "传统_担保费率低于1%（含）_在保余额", "传统_本月解保_在保余额", "传统_本年解保_在保余额",
        "传统_当年_驿享贷_名义放款"
    ] + [f"传统_{lvl}_在保余额" for lvl in ["正常","关注","次级","可疑","损失"]]

    out = {n: calc_metric(n) for n in 指标列表}

    # 额外汇总
    df["客户名称"] = df["客户名称"].astype(str).str.strip()
    df_valid = df[~df["客户名称"].str.match(r"^\d*$")]
    df_sum   = (df_valid.groupby("客户名称", as_index=False)["在保余额"]
                      .sum().rename(columns={"在保余额":"客户在保余额汇总"}))
    small_names = df_valid[df_valid["企业类别"].isin(["小型","微型"])]["客户名称"].drop_duplicates()
    df_small_sum = df_sum.merge(small_names, on="客户名称", how="inner")

    out["单户担保500万以下小微余额"] = df_small_sum.loc[df_small_sum["客户在保余额汇总"] < 500,
                                                       "客户在保余额汇总"].sum()
    out["前十大客户在保余额"] = df_sum.nlargest(10, "客户在保余额汇总")["客户在保余额汇总"].sum()
    out["最大单一客户在保余额"] = df_sum["客户在保余额汇总"].max()

    return pd.Series(out)

# ────────────────────────────
# ② Streamlit 页面 / 两页切换
# ────────────────────────────
st.set_page_config(page_title="担保业务统计工具", layout="wide")
page = st.sidebar.radio("📑 页面导航", ["① 上传与运行", "② 统计结果", "③ 在保余额检查"])

# ---------- ① 上传与运行 ----------
if page == "① 上传与运行":
    st.title("📊 担保业务统计工具（Streamlit 版）")

    col1, col2 = st.columns(2)
    with col1:
        ledger_file = st.file_uploader("台账.xlsx", type="xlsx", key="ledger")
    with col2:
        filter_file = st.file_uploader("筛选条件.xlsx", type="xlsx", key="filter")

    as_of = st.date_input("统计基准日期", datetime.today(), key="as_of")

    if st.button("🚀 执行统计", use_container_width=True):
        if not (ledger_file and filter_file):
            st.error("请同时上传【台账.xlsx】和【筛选条件.xlsx】")
            st.stop()

        with st.spinner("读取并处理数据…"):
            df_data    = load_data(ledger_file, filter_file)
            ser_result = calc_metrics(df_data, pd.to_datetime(as_of))
            df_overdue = df_data[
                (df_data["实际到期时间"].notna()) &
                (df_data["实际到期时间"] < pd.Timestamp.today().normalize()) &
                (df_data["在保余额"] != 0)
            ]
        st.session_state["result"] = ser_result
        st.session_state["overdue"] = df_overdue
        st.success("✅ 统计完成！左栏切到 **② 统计结果** 查看/下载")

# ---------- ② 统计结果 ----------
elif page == "② 统计结果":
    st.title("📈 统计结果预览 / 下载")

    if "result" not in st.session_state:
        st.warning("⚠️ 还没有统计结果，请先去 **① 上传与运行** 执行一次。")
        st.stop()

    ser_res = st.session_state["result"]

    # ========== 下载按钮先放最上面 ==========
    out = BytesIO()
    (ser_res.rename_axis("指标").reset_index().to_excel(out, index=False))

    st.download_button(
        "💾 下载结果 Excel",
        data=out.getvalue(),
        file_name=f"统计结果_{datetime.today():%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    # -------- 结果表 & 图表 --------
    st.subheader("📋 结果表")
    st.dataframe(ser_res.to_frame("数值"))

    st.subheader("📊 前 10 指标")
    st.bar_chart(ser_res.head(10))
# ---------- ③ 在保余额检查 ----------
else:   # page == "③ 在保余额检查"
    st.title("⏰ 在保余额检查")

    if "overdue" not in st.session_state:
        st.warning("⚠️ 还没有统计结果，请先去 ① 上传并执行。")
        st.stop()

    df_overdue = st.session_state["overdue"]

    if df_overdue.empty:
        st.success("🎉 没有发现到期未清零记录，一切正常！")
    else:
        st.info(f"共有 **{len(df_overdue)}** 行到期在保余额未清零：")
        st.dataframe(df_overdue, use_container_width=True)

        # 下载按钮放最上方
        out2 = BytesIO()
        df_overdue.to_excel(out2, index=False)
        st.download_button(
            "💾 下载在保余额明细 Excel",
            data=out2.getvalue(),
            file_name=f"在保余额未清零_{datetime.today():%Y%m%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
