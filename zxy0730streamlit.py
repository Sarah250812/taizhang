# app.py ── Streamlit 版台账统计
import streamlit as st
import pandas as pd
import numpy as np
from pathlib import Path
from functools import reduce
from datetime import datetime
from io import BytesIO

# ────────────────────────────────────
# ① 公共函数（改自你原脚本，删掉 input / Path 依赖）
# ────────────────────────────────────
def guess_sheet_name(xl: pd.ExcelFile) -> str:
    for name in xl.sheet_names:
        if "台账" in name or "总台账" in name:
            return name
    return xl.sheet_names[0]

def load_data(ledger_file, filter_file) -> pd.DataFrame:
    """ledger_file / filter_file 均为 UploadedFile（或 BytesIO）"""
    xl = pd.ExcelFile(ledger_file)
    sheet = guess_sheet_name(xl)
    st.info(f"📄 自动识别工作表：**{sheet}**")
    df = xl.parse(sheet_name=sheet, header=2)

    df_map = pd.read_excel(filter_file, sheet_name="业务分类")
    gov_list = (
        pd.read_excel(filter_file, sheet_name="国企名单", usecols=["客户名称"])
          .iloc[:, 0].astype(str).str.strip().tolist()
    )

    df["客户名称"] = df["客户名称"].astype(str).str.strip()
    df["业务品种"] = df["业务品种"].astype(str).str.strip()
    df["国企民企"] = np.where(
        df["客户名称"].isin(gov_list) | (df["业务品种"] == "委托贷款"), "国企", "民企"
    )

    df = df.merge(df_map, how="left", on="业务品种")

    # 列名清洗
    df.columns = (
        df.columns
          .str.replace(r"\s+", "", regex=True)
          .str.replace(r"[（(]\s*(?:万元|%)\s*[）)]", "", regex=True)
    )
    df["实际放款"] = df["放款金额"] - df["待放款金额"]
    df["放款时间"]   = pd.to_datetime(df["放款时间"], errors="coerce")
    df["实际到期时间"] = pd.to_datetime(df["实际到期时间"], errors="coerce")
    return df

def calc_metrics(df: pd.DataFrame, as_of: pd.Timestamp) -> pd.Series:
    year_start = as_of.replace(month=1, day=1)
    year_end   = as_of.replace(month=12, day=31)
    month_start = as_of.replace(day=1)
    month_end   = (month_start + pd.offsets.MonthEnd(0))

    # ----- 规则与聚合映射（保持原逻辑） -----
    RULES = {
        "当年": lambda d: d["放款时间"].between(year_start, year_end) & (d["放款金额"] > 0),
        "当月": lambda d: d["放款时间"].between(month_start, month_end) & (d["放款金额"] > 0),
        "本月解保": lambda d: d["实际到期时间"].between(month_start, month_end),
        "本年解保": lambda d: d["实际到期时间"].between(year_start, year_end),
        "在保": lambda d: d["在保余额"] > 0,
        "传统": lambda d: d["业务品种2"].isin(["传统"]),
        "全担": lambda d: d["公司责任风险比例"] == "100%",
        "惠蓉贷": lambda d: d["业务品种3"] == "惠蓉贷",
        "驿享贷": lambda d: d["业务品种"] == "驿享贷",
        "担保费率低于1%（含）": lambda d: d["担保费率/利率"] <= 1,
        "小微": lambda d: d["企业类别"].isin(["小型", "微型"]),
        "中型": lambda d: d["企业类别"] == "中型",
        "中小": lambda d: d["企业类别"].isin(["小型", "微型", "中型"]),
        "支农支小": lambda d: d["企业类别"].isin(["小型", "微型", "三农"]),
        "传统个体工商户及小微企业主": lambda d: d["业务品种"] == "惠抵贷",
        "农户及新型农业经营主体": lambda d: d["企业类别"].isin(["三农"]),
        "新增": lambda d: d["新增/续贷"] == "新增",
        "民企": lambda d: d["国企民企"] == "民企",
        "国企": lambda d: d["国企民企"] == "国企",
    }
    RULES.update({lvl: lambda d, _lvl=lvl: d["风险等级"] == _lvl
                  for lvl in ["正常", "关注", "次级", "可疑", "损失"]})

    AGG_MAP = {
        "名义放款": ("放款金额", "sum"),
        "实际放款": ("实际放款", "sum"),
        "在保余额": ("在保余额", "sum"),
        "笔数":     (None, "count"),
        "户数":     ("客户名称", "nunique"),
    }

    def calc_metric(metric_name: str):
        parts     = metric_name.split("_")
        agg_key   = parts[-1]
        rule_keys = parts[:-1]
        mask = reduce(lambda a, b: a & b,
                      [RULES[k](df) for k in rule_keys],
                      pd.Series(True, index=df.index))
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
    ] + [f"传统_{lvl}_在保余额" for lvl in ["正常", "关注", "次级", "可疑", "损失"]]

    result = {n: calc_metric(n) for n in 指标列表}

    # ——附加汇总（过滤掉纯数字客户名）——
    df["客户名称"] = df["客户名称"].astype(str).str.strip()
    valid = ~df["客户名称"].str.match(r"^\d*$")
    df_valid = df[valid]

    df_sum = (df_valid.groupby("客户名称", as_index=False)["在保余额"]
                      .sum().rename(columns={"在保余额": "客户在保余额汇总"}))
    df_small = df_valid[df_valid["企业类别"].isin(["小型", "微型"])]
    small_names = df_small["客户名称"].drop_duplicates()
    df_small_sum = df_sum.merge(small_names, on="客户名称", how="inner")

    result["单户担保500万以下小微余额"] = df_small_sum.loc[
        df_small_sum["客户在保余额汇总"] < 500, "客户在保余额汇总"].sum()
    result["前十大客户在保余额"] = df_sum.nlargest(10, "客户在保余额汇总")["客户在保余额汇总"].sum()
    result["最大单一客户在保余额"] = df_sum["客户在保余额汇总"].max()

    return pd.Series(result)

# ────────────────────────────────────
# ② Streamlit 页面
# ────────────────────────────────────
st.set_page_config(page_title="担保业务统计工具", layout="wide")
st.title("📊 担保业务统计工具（Streamlit 版）")

col_file1, col_file2 = st.columns(2)
with col_file1:
    ledger_file = st.file_uploader("台账.xlsx", type="xlsx")
with col_file2:
    filter_file = st.file_uploader("筛选条件.xlsx", type="xlsx")

as_of = st.date_input("统计基准日期", datetime.today())

if st.button("🚀 执行统计"):

    if not (ledger_file and filter_file):
        st.error("请同时上传【台账.xlsx】和【筛选条件.xlsx】")
        st.stop()

    with st.spinner("读取并处理数据…"):
        df_data = load_data(ledger_file, filter_file)
        ser_res = calc_metrics(df_data, pd.to_datetime(as_of))

    st.success("✅ 统计完成")
    st.subheader("结果表")
    st.dataframe(ser_res.to_frame("数值"))

    # 可视化示例：展示前 10 条
    st.bar_chart(ser_res.head(10))

    # 下载按钮
    out = BytesIO()
    ser_res.to_frame("数值").to_excel(out, index=False)
    st.download_button("💾 下载结果 Excel",
                       data=out.getvalue(),
                       file_name=f"统计结果_{as_of:%Y%m%d}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
else:
    st.info("👆 先上传文件，然后点击执行")
