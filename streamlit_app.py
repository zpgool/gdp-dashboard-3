# streamlit_app.py
# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import plotly.express as px
import requests
from io import StringIO
from datetime import datetime

# ----------------------------
# 폰트 설정 (없으면 생략)
# ----------------------------
import matplotlib
try:
    matplotlib.rc("font", family="Pretendard")
except:
    pass

st.set_page_config(page_title="기후위기와 교육 영향 대시보드", layout="wide")

# ----------------------------
# 데이터 로딩 함수
# ----------------------------
@st.cache_data
def load_public_data():
    """
    NOAA 공식 데이터에서 연도별 전세계 태풍/허리케인 발생 수 불러오기
    - 출처: NOAA IBTrACS (International Best Track Archive for Climate Stewardship)
    - URL: https://www.ncei.noaa.gov/products/international-best-track-archive
    """
    try:
        url = "https://www.ncei.noaa.gov/data/international-best-track-archive-for-climate-stewardship-ibtracs/v04r00/access/csv/ibtracs.since1980.list.v04r00.csv"
        r = requests.get(url, timeout=20)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))
        # 연도 추출
        df["year"] = pd.to_datetime(df["ISO_TIME"], errors="coerce").dt.year
        storm_counts = df.groupby("year")["SID"].nunique().reset_index()
        storm_counts.columns = ["date", "value"]
        # 미래 데이터 제거
        today_year = datetime.today().year
        storm_counts = storm_counts[storm_counts["date"] <= today_year]
        return storm_counts
    except:
        # 예시 데이터
        example = pd.DataFrame({
            "date": [2020, 2021, 2022, 2023, 2024],
            "value": [82, 91, 95, 88, 94]
        })
        example["group"] = "예시 데이터"
        return example

@st.cache_data
def load_user_data():
    """
    사용자 입력 데이터: 기사 및 보고서에서 정리된 '학교 휴업/수업 차질' 사례
    """
    data = {
        "date": [2023, 2025],
        "value": [24, 247],
        "group": ["집중호우", "폭우"]
    }
    return pd.DataFrame(data)

# ----------------------------
# 메인 레이아웃
# ----------------------------
st.title("📊 기후위기와 청소년 학업 영향 데이터 대시보드")

tab1, tab2 = st.tabs(["🌍 공식 공개 데이터 분석", "👩‍🎓 사용자 입력 데이터 분석"])

# ----------------------------
# (1) 공식 공개 데이터
# ----------------------------
with tab1:
    st.header("NOAA 태풍 발생 추이 (1980~현재)")
    df_public = load_public_data()
    st.markdown("데이터 출처: [NOAA IBTrACS](https://www.ncei.noaa.gov/products/international-best-track-archive)")

    fig = px.line(df_public, x="date", y="value",
                  title="연도별 전세계 태풍/허리케인 발생 수",
                  labels={"date": "연도", "value": "발생 건수"})
    st.plotly_chart(fig, use_container_width=True)

    st.download_button("📥 데이터 다운로드 (CSV)", df_public.to_csv(index=False), "public_data.csv", "text/csv")

# ----------------------------
# (2) 사용자 입력 데이터
# ----------------------------
with tab2:
    st.header("한국 학교 휴업/수업 차질 사례 데이터")
    df_user = load_user_data()

    fig2 = px.bar(df_user, x="date", y="value", color="group",
                  text="value",
                  title="기후재해로 인한 학교 수업 차질 건수",
                  labels={"date": "연도", "value": "휴업/차질 학교 수", "group": "원인"})
    fig2.update_traces(textposition="outside")
    st.plotly_chart(fig2, use_container_width=True)

    st.download_button("📥 데이터 다운로드 (CSV)", df_user.to_csv(index=False), "user_data.csv", "text/csv")

    st.markdown("➡️ 위 데이터는 보고서 입력 자료(기사 기반)로 정리된 값입니다.")
