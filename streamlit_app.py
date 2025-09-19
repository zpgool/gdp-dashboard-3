# streamlit_app.py
"""
Streamlit 앱: 기후재해로 인한 청소년 수업 차질 대시보드
- 역할: (1) 공개 데이터 대시보드 (공식 출처 시도, 실패 시 예시 데이터로 대체)
        (2) 사용자 입력 대시보드 (프롬프트에 제공된 통계/텍스트만 사용, 실행 중 추가 업로드 X)
요구사항 반영:
- 한글 UI, Pretendard 폰트 시도, @st.cache_data 사용, 전처리·미래 데이터 제거, CSV 다운로드 버튼 제공
- 데이터 표준화: date, value, group(optional)
- 코드 주석에 출처(URL) 명시 (실제 데이터 API가 있을 경우 시도)
- 로컬 자정(Asia/Seoul 기준) 이후의 데이터 제거
- 사이드바 필터 자동 구성
참고(예시) 출처 주석:
 - 교육부/지역 발표(뉴스 기사): https://www.hani.co.kr/arti/society/schooling/1208715.html
 - 2023 집중호우 보도(뉴스): https://www.newsis.com/view/?id=NISX20230716_0002378455
 - 태풍·기후 데이터(기상/기후): NOAA, NASA, KMA 자료(실제 API 사용 시 교체 권장)
    NOAA: https://www.ncei.noaa.gov/
    NASA GPM (강수량): https://gpm.nasa.gov/
    KMA (기상자료): https://www.kma.go.kr/
 - 지역 기사 예: https://www.kado.net/news/articleView.html?idxno=1198111
(주의) 본 코드는 실행 시 외부 API 접속을 시도합니다. 실패하면 내부 예시 데이터로 자동 전환하고 안내 메시지를 표시합니다.
"""

from datetime import datetime, timedelta, timezone
import io
import sys
import os
import json

import pandas as pd
import numpy as np
import requests
import plotly.express as px
import pydeck as pdk
import streamlit as st

# ---------------------------
# 설정: 로컬 타임존(Asia/Seoul) 기준 자정 계산
# ---------------------------
SEOUL_TZ = timezone(timedelta(hours=9))
def seoul_now():
    return datetime.now(SEOUL_TZ)

def seoul_midnight_today():
    now = seoul_now()
    return datetime(year=now.year, month=now.month, day=now.day, tzinfo=SEOUL_TZ)

CUTOFF = seoul_midnight_today()  # 오늘(로컬 자정) 이후의 데이터는 제거

# ---------------------------
# Pretendard 폰트 시도 (없으면 무시)
# ---------------------------
st.set_page_config(page_title="기후위기·수업 차질 대시보드", layout="wide")
st.markdown(
    """
    <style>
    @font-face {
        font-family: 'PretendardCustom';
        src: url('/fonts/Pretendard-Bold.ttf') format('truetype');
        font-weight: 700;
        font-style: normal;
    }
    html, body, [class*="css"]  {
        font-family: PretendardCustom, Pretendard, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# 유틸리티: CSV 다운로드 버튼 (DataFrame -> csv buffer)
# ---------------------------
def get_csv_download_link(df: pd.DataFrame, filename: str, label: str):
    csv = df.to_csv(index=False).encode('utf-8-sig')
    return st.download_button(label=label, data=csv, file_name=filename, mime='text/csv')

# ---------------------------
# 데이터 로드 함수: 공개 데이터 시도 (캐시)
# ---------------------------
@st.cache_data(ttl=3600)
def load_official_datasets():
    """
    가능한 공식 출처를 순서대로 시도해서 데이터를 가져옵니다.
    - 실패 시 예시(sample) 데이터로 대체
    반환: dict of DataFrames with keys: 'precip_ts', 'school_actions', 'school_damage_geo'
    """
    messages = []
    # 1) 시도: NASA / GPM 월별 전지구 강수량(예시) - (실제 API 교체 권장)
    #    (여기서는 public API 호출 예시를 시도합니다; 실패하면 내부 데이터 사용)
    try:
        # Dummy example: pretend to fetch monthly precipitation index from NOAA/NASA
        # NOTE: Replace below URL with real dataset API if available.
        nasa_url = "https://data.nasa.gov/resource/example_gpm_monthly_precip.json"
        r = requests.get(nasa_url, timeout=6)
        if r.status_code == 200:
            data = r.json()
            # Normalize to DataFrame (this block is placeholder; real API will differ)
            precip_df = pd.json_normalize(data)
            # Attempt best-effort parse
            if 'date' in precip_df.columns and 'precip' in precip_df.columns:
                precip_df = precip_df.rename(columns={'precip': 'value', 'date': 'date'})
                precip_df['date'] = pd.to_datetime(precip_df['date'], errors='coerce')
                precip_df = precip_df[['date', 'value']].dropna()
            else:
                raise ValueError("NASA response format unexpected")
            messages.append("NASA GPM 데이터 로드 성공")
        else:
            raise Exception(f"NASA 요청 상태 {r.status_code}")
    except Exception as e:
        messages.append("NASA/NOAA 호출 실패: 내부 예시 데이터로 대체")
        # 내부 예시: 연도별(2015-2025) 강수 이벤트 지수 (샘플)
        years = pd.date_range(start="2015-01-01", end="2025-07-01", freq="YS")
        precip_df = pd.DataFrame({
            'date': years,
            'value': [np.random.uniform(20, 80) + (i*3) for i in range(len(years))]  # 증가 추이 모사
        })

    # 2) 시도: 교육부/뉴스에서 집계된 '학교 수업 조치' 시계열 (예시)
    try:
        # No official direct CSV; attempt to query hypothetical endpoint
        edu_url = "https://api.moe.go.kr/school-actions/example_school_actions.csv"
        r2 = requests.get(edu_url, timeout=6)
        if r2.status_code == 200:
            school_actions = pd.read_csv(io.StringIO(r2.text))
            # standardize
            if 'date' not in school_actions.columns:
                # try to find date-like column
                school_actions.rename(columns={school_actions.columns[0]:'date'}, inplace=True)
            school_actions['date'] = pd.to_datetime(school_actions['date'], errors='coerce')
            # Ensure value columns exist
            if 'value' not in school_actions.columns:
                # sum of action counts into 'value'
                numeric_cols = school_actions.select_dtypes(include='number').columns
                if len(numeric_cols) > 0:
                    school_actions['value'] = school_actions[numeric_cols].sum(axis=1)
                else:
                    school_actions['value'] = 0
            school_actions = school_actions[['date','value']].dropna()
            messages.append("교육부 학교조치 데이터 로드 성공")
        else:
            raise Exception(f"교육부 요청 상태 {r2.status_code}")
    except Exception as e:
        messages.append("교육부/뉴스 API 호출 실패: 내부 예시 데이터로 대체")
        # 내부 예시: 특정 날짜별 학교 조치 건수 (샘플)
        dates = pd.to_datetime([
            "2023-07-16","2023-08-10","2024-07-20","2025-07-18","2025-03-19"
        ])
        values = [24, 5, 40, 247, 12]  # 사용자 제공 통계 반영 예시
        school_actions = pd.DataFrame({'date': dates, 'value': values})

    # 3) 시도: 학교 피해 지리정보 (위도/경도) - 예시
    try:
        geo_url = "https://data.kostat.go.kr/example/school_damage_geo.geojson"
        r3 = requests.get(geo_url, timeout=6)
        if r3.status_code == 200:
            geo_json = r3.json()
            # For simplicity, create DataFrame of features with lon/lat and damage_count
            feats = geo_json.get('features', [])
            rows = []
            for f in feats:
                props = f.get('properties', {})
                geom = f.get('geometry', {})
                coords = geom.get('coordinates', [None, None])
                rows.append({
                    'lon': coords[0],
                    'lat': coords[1],
                    'value': props.get('damage_count', 1),
                    'name': props.get('name', '학교')
                })
            school_damage_geo = pd.DataFrame(rows)
            messages.append("지리 데이터 로드 성공")
        else:
            raise Exception(f"지리 데이터 요청 상태 {r3.status_code}")
    except Exception as e:
        messages.append("지리/위치 데이터 로드 실패: 내부 예시 데이터로 대체")
        # 내부 예시: 몇개 지역 포인트
        school_damage_geo = pd.DataFrame({
            'name': ['청주 지역학교','진천 학교','옥천 학교','영동 학교','괴산 학교'],
            'lat': [36.642, 36.873, 36.305, 36.118, 36.606],
            'lon': [127.489, 127.327, 127.654, 127.761, 127.957],
            'value': [11,3,2,2,2]
        })

    # 전처리: 표준화 및 미래 데이터 제거
    for df in [precip_df, school_actions]:
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df = df.dropna(subset=['date'])
    # remove future dates beyond today midnight (Asia/Seoul)
    def remove_future_dates(df):
        if 'date' in df.columns:
            return df[df['date'] < CUTOFF].copy()
        else:
            return df
    precip_df = remove_future_dates(precip_df)
    school_actions = remove_future_dates(school_actions)

    return {
        'precip_ts': precip_df.reset_index(drop=True),
        'school_actions': school_actions.reset_index(drop=True),
        'school_damage_geo': school_damage_geo.reset_index(drop=True),
        'messages': messages
    }

# ---------------------------
# 사용자 입력(프롬프트 내 통계) -> 내부로직으로만 사용 (앱 실행 중 업로드 금지)
# ---------------------------
@st.cache_data
def build_user_input_dataset():
    """
    사용자가 제공한 Input 섹션의 통계/텍스트만을 사용해 DataFrame 생성.
    아래 항목은 프롬프트에 제공된 통계들을 표준화(date, value, group)
    """
    rows = []
    # From prompt examples:
    # 2023-07 집중호우: 24개 학교 휴업/원격수업
    rows.append({'date': pd.to_datetime("2023-07-16"), 'value': 24, 'group': '휴업/원격/조치', 'note':'2023년 7월 집중호우(뉴스)'} )
    # 태풍 카눈 2023-08-09 강원도 5개 휴교
    rows.append({'date': pd.to_datetime("2023-08-09"), 'value': 5, 'group': '휴업/원격/조치', 'note':'태풍 카눈(강원도)'})
    # 2025-07 폭우: 247개 학교 학사일정 조정 등(세부수치은 별도)
    rows.append({'date': pd.to_datetime("2025-07-18"), 'value': 247, 'group': '학사일정 조정', 'note':'2025-07 전국 폭우(한겨레 기사)'} )
    # 2025-03 폭설 일부 학교 휴업 (예: 12)
    rows.append({'date': pd.to_datetime("2025-03-19"), 'value': 12, 'group': '휴업/원격/조치', 'note':'2025-03 강원도 폭설(EBS)'} )
    # 충북 호우 피해 2023-07-16: 피해 학교·유치원 24곳 (지역 breakdown exists)
    # We'll also add regional breakdown entries from prompt
    rows.extend([
        {'date': pd.to_datetime("2023-07-16"), 'value': 11, 'group': '청주 피해 학교', 'note':'충북 청주 피해 학교수'},
        {'date': pd.to_datetime("2023-07-16"), 'value': 3,  'group': '진천 피해 학교', 'note':'충북 진천'},
        {'date': pd.to_datetime("2023-07-16"), 'value': 2,  'group': '옥천 피해 학교', 'note':'충북 옥천'},
        {'date': pd.to_datetime("2023-07-16"), 'value': 2,  'group': '영동 피해 학교', 'note':'충북 영동'},
        {'date': pd.to_datetime("2023-07-16"), 'value': 2,  'group': '괴산 피해 학교', 'note':'충북 괴산'},
        {'date': pd.to_datetime("2023-07-16"), 'value': 1,  'group': '제천 피해 학교', 'note':'충북 제천'},
        {'date': pd.to_datetime("2023-07-16"), 'value': 1,  'group': '보은 피해 학교', 'note':'충북 보은'}
    ])
    df = pd.DataFrame(rows)
    # 표준화: ensure date,value,group exist
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df = df.dropna(subset=['date'])
    df['value'] = pd.to_numeric(df['value'], errors='coerce').fillna(0).astype(int)
    # remove future dates beyond cutoff (per rules)
    df = df[df['date'] < CUTOFF].reset_index(drop=True)
    return df

# ---------------------------
# 메인 UI
# ---------------------------
st.title("기후위기(폭우·태풍 등) → 청소년 수업 차질 대시보드")
st.caption("공개 데이터(공식 출처 시도)와 사용자 입력(프롬프트 통계)을 각각 시각화합니다. 모든 라벨은 한국어입니다.")

# Load official datasets (with caching)
with st.spinner("공개 데이터 불러오는 중... (공식 출처 시도)"):
    data_bundle = load_official_datasets()
precip = data_bundle['precip_ts']
school_actions = data_bundle['school_actions']
school_geo = data_bundle['school_damage_geo']
for msg in data_bundle.get('messages', []):
    st.info(msg)

# 탭 구성: 공개 데이터 / 사용자 입력
tab1, tab2 = st.tabs(["📡 공개 데이터 대시보드", "📝 사용자 입력 대시보드"])

# ---------------------------
# 탭1: 공개 데이터
# ---------------------------
with tab1:
    st.header("공개 데이터 기반 분석 (공식 출처 시도)")
    st.markdown("**출처(예시)**: 교육부/뉴스 기사(한겨레, 뉴시스), 기상·기후(국제: NOAA/NASA, 국내: KMA). 코드 내부 주석에 상세 출처 표기.")
    col1, col2 = st.columns([2,1])
    with col1:
        st.subheader("연도별(또는 시계열) 강수/기상 지표 (예시)")
        if precip is None or precip.empty:
            st.warning("강수 시계열 데이터가 없습니다. 내부 예시 데이터가 사용되었습니다.")
        else:
            st.write("데이터 미리보기:")
            st.dataframe(precip.head(10))
        # 기본 플롯: 꺾은선 (연도/시계열)
        if not precip.empty:
            # 자동 사이드바 옵션: 기간 필터 / 스무딩(이동평균)
            min_date = precip['date'].min().date()
            max_date = precip['date'].max().date()
            with st.expander("시계열 필터 옵션"):
                start = st.date_input("시작일", value=min_date, min_value=min_date, max_value=max_date, key="precip_start")
                end = st.date_input("종료일", value=max_date, min_value=min_date, max_value=max_date, key="precip_end")
                window = st.slider("이동평균 윈도우(기간)", min_value=1, max_value=12, value=1, key="precip_ma")
            mask = (precip['date'].dt.date >= start) & (precip['date'].dt.date <= end)
            df_plot = precip.loc[mask].copy()
            df_plot = df_plot.sort_values('date')
            if window > 1:
                df_plot['value_smooth'] = df_plot['value'].rolling(window=window, min_periods=1).mean()
                fig = px.line(df_plot, x='date', y='value_smooth', labels={'value_smooth':'값(이동평균)','date':'날짜'}, title="강수량 지표(이동평균)")
            else:
                fig = px.line(df_plot, x='date', y='value', labels={'value':'값','date':'날짜'}, title="강수량 지표")
            fig.update_layout(xaxis_title="날짜", yaxis_title="강수 지표 (임의 단위)")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("강수 시계열 데이터가 없어 예시 그래프를 표시합니다.")
            # 예시 그래프: 랜덤 생성 (이미 내부 예시 데이터 있음)
            sample = precip.copy()
            if not sample.empty:
                fig = px.line(sample, x='date', y='value', labels={'value':'값','date':'날짜'}, title="강수량 지표 (예시)")
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.write("데이터 없음")

    with col2:
        st.subheader("학교 조치(휴업/원격/단축 등) 시계열")
        st.write("데이터 미리보기:")
        st.dataframe(school_actions.head(10))
        if not school_actions.empty:
            # 자동 사이드바 옵션: 집계단위(날/월/연)
            agg_opt = st.selectbox("집계 단위 선택", options=['일별','월별','연별'], index=1, key='agg_school')
            df_sa = school_actions.copy()
            if agg_opt == '월별':
                df_sa['period'] = df_sa['date'].dt.to_period('M').dt.to_timestamp()
            elif agg_opt == '연별':
                df_sa['period'] = df_sa['date'].dt.to_period('Y').dt.to_timestamp()
            else:
                df_sa['period'] = df_sa['date'].dt.floor('D')
            df_agg = df_sa.groupby('period', as_index=False)['value'].sum().sort_values('period')
            fig2 = px.bar(df_agg, x='period', y='value', labels={'period':'기간','value':'조치 건수'}, title="학교 조치 건수 추이")
            st.plotly_chart(fig2, use_container_width=True)
            # CSV 다운로드
            get_csv_download_link(df_agg, "public_school_actions_agg.csv", "학교 조치 집계 CSV 다운로드")
        else:
            st.info("공개된 학교 조치 데이터가 없습니다. 내부 예시 데이터를 사용합니다.")

    st.subheader("학교 피해 위치 지도 (예시·샘플)")
    if school_geo is not None and not school_geo.empty:
        st.write("지도 데이터 미리보기:")
        st.dataframe(school_geo.head(10))
        # pydeck 지도
        if {'lat','lon'}.issubset(set(school_geo.columns)):
            midpoint = (float(school_geo['lat'].mean()), float(school_geo['lon'].mean()))
            st.pydeck_chart(pdk.Deck(
                map_style='mapbox://styles/mapbox/light-v9',
                initial_view_state=pdk.ViewState(
                    latitude=midpoint[0],
                    longitude=midpoint[1],
                    zoom=7,
                    pitch=0,
                ),
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=school_geo,
                        get_position='[lon, lat]',
                        get_radius='value * 200',
                        radius_min_pixels=5,
                        radius_max_pixels=100,
                        get_fill_color='[255, 100, 100, 140]',
                        pickable=True,
                    )
                ],
                tooltip={"text": "{name}\n피해건수: {value}"}
            ))
            get_csv_download_link(school_geo, "public_school_damage_geo.csv", "학교 피해 위치 CSV 다운로드")
        else:
            st.warning("학교 지리데이터에 lat/lon 컬럼이 필요합니다.")
    else:
        st.info("학교 피해 위치 데이터가 없습니다.")

    st.markdown("---")
    st.markdown("**[알림]**: 위 공개 데이터는 앱 실행 시 외부 API를 시도해 가져오며, API 실패 시 내부 예시 데이터로 대체됩니다. 코드 주석의 출처(뉴스/기상 데이터)를 참조하세요.")

# ---------------------------
# 탭2: 사용자 입력 (프롬프트의 통계만 사용)
# ---------------------------
with tab2:
    st.header("사용자 입력 대시보드 (프롬프트 내 제공 데이터만 사용)")
    st.markdown("앱 실행 중 파일 업로드를 요구하지 않습니다. 아래 시각화는 프롬프트에 제공된 통계(연도별/사건별 학교 조치 및 지역별 피해)를 사용해 생성되었습니다.")

    user_df = build_user_input_dataset()
    st.subheader("데이터 표준화 미리보기")
    st.dataframe(user_df)

    # 자동 사이드바 옵션: 필터(그룹), 기간
    st.subheader("대시보드 컨트롤")
    groups = sorted(user_df['group'].unique().tolist())
    sel_groups = st.multiselect("그룹 선택 (기본: 전체)", options=groups, default=groups, key='user_groups')
    min_date = user_df['date'].min().date()
    max_date = user_df['date'].max().date()
    start = st.date_input("시작일", value=min_date, min_value=min_date, max_value=max_date, key='user_start')
    end = st.date_input("종료일", value=max_date, min_value=min_date, max_value=max_date, key='user_end')
    df_filtered = user_df[(user_df['date'].dt.date >= start) & (user_df['date'].dt.date <= end)]
    if sel_groups:
        df_filtered = df_filtered[df_filtered['group'].isin(sel_groups)]

    st.subheader("시계열: 학교 조치 / 사건별 건수")
    # If multiple dates per year, use line/area; else bar
    df_ts = df_filtered.groupby('date', as_index=False)['value'].sum().sort_values('date')
    if df_ts.empty:
        st.info("선택된 조건의 데이터가 없습니다.")
    else:
        # Choose plot type by number of distinct dates
        if df_ts['date'].nunique() > 6:
            fig_u = px.area(df_ts, x='date', y='value', labels={'date':'날짜','value':'건수'}, title="학교 조치(시계열)")
        else:
            fig_u = px.bar(df_ts, x='date', y='value', labels={'date':'날짜','value':'건수'}, title="학교 조치(사건별)")
        st.plotly_chart(fig_u, use_container_width=True)

    st.subheader("그룹별 분포 (원그래프 / 막대)")
    df_group = df_filtered.groupby('group', as_index=False)['value'].sum().sort_values('value', ascending=False)
    if not df_group.empty:
        fig_pie = px.pie(df_group, names='group', values='value', title="그룹별 합계(비율)")
        fig_bar = px.bar(df_group, x='group', y='value', labels={'group':'그룹','value':'합계'}, title="그룹별 합계(막대)")
        st.plotly_chart(fig_pie, use_container_width=True)
        st.plotly_chart(fig_bar, use_container_width=True)
        get_csv_download_link(df_filtered, "user_input_filtered.csv", "사용자 입력(필터된) CSV 다운로드")
    else:
        st.info("그룹별 데이터 없음")

    st.subheader("지역별 피해(프롬프트 지역내역 기반)")
    # Build small map from user_df region groups that contain '피해' or known region names
    region_df = user_df[user_df['group'].str.contains('피해|청주|진천|옥천|영동|괴산|제천|보은', na=False)].copy()
    # assign approximate coords (from earlier internal sample in load_official_datasets); if missing, skip map
    coord_map = {
        '청주 피해 학교': (36.642,127.489),
        '진천 피해 학교': (36.873,127.327),
        '옥천 피해 학교': (36.305,127.654),
        '영동 피해 학교': (36.118,127.761),
        '괴산 피해 학교': (36.606,127.957),
        '제천 피해 학교': (37.128,128.194),
        '보은 피해 학교': (36.487,127.721)
    }
    if not region_df.empty:
        rows = []
        for _, r in region_df.iterrows():
            grp = r['group']
            if grp in coord_map:
                lat, lon = coord_map[grp]
                rows.append({'name':grp, 'lat':lat, 'lon':lon, 'value':int(r['value'])})
        if rows:
            reg_df = pd.DataFrame(rows)
            st.dataframe(reg_df)
            midpoint = (float(reg_df['lat'].mean()), float(reg_df['lon'].mean()))
            st.pydeck_chart(pdk.Deck(
                map_style='mapbox://styles/mapbox/light-v9',
                initial_view_state=pdk.ViewState(
                    latitude=midpoint[0],
                    longitude=midpoint[1],
                    zoom=8,
                    pitch=0,
                ),
                layers=[
                    pdk.Layer(
                        "ScatterplotLayer",
                        data=reg_df,
                        get_position='[lon, lat]',
                        get_radius='value * 300',
                        radius_min_pixels=5,
                        radius_max_pixels=200,
                        get_fill_color='[50, 130, 200, 160]',
                        pickable=True,
                    )
                ],
                tooltip={"text": "{name}\n피해 학교수: {value}"}
            ))
            get_csv_download_link(reg_df, "user_region_damage.csv", "지역 피해 CSV 다운로드")
        else:
            st.info("지역 좌표 매핑 가능한 항목이 없습니다.")
    else:
        st.info("프롬프트에 지역 피해 데이터가 포함되어 있지 않습니다.")

    st.markdown("---")
    st.subheader("요약 및 권장 시각화")
    st.markdown("""
    - 제공된 통계(2023-07: 24개, 2023-08 태풍 카눈: 5개, 2025-07: 247개 등)를 기반으로 **시계열(연/월별 추이), 그룹별 비율(원/막대), 지역 분포 지도** 등을 자동 생성했습니다.
    - 장기적으로는 기상(강수) 시계열과 학교 조치 시계열을 병렬로 보여주어 상관/연관을 탐색하는 것을 권장합니다.
    """)

# ---------------------------
# 하단: 추가 안내(간단)
# ---------------------------
st.sidebar.header("앱 정보")
st.sidebar.write("이 앱은 Streamlit + GitHub Codespaces 환경에서 즉시 실행 가능한 형태로 작성되었습니다.\n\n- 외부 API 호출 실패 시 내부 예시 데이터로 자동 대체됩니다.\n- Pretendard 폰트는 /fonts/Pretendard-Bold.ttf 경로에서 시도하며, 없으면 시스템 폰트로 대체됩니다.\n- 코드 수정 시 주석에 표기된 출처(URL)를 실제 데이터셋 엔드포인트로 교체하세요.")

st.sidebar.header("개발자 노트")
st.sidebar.write("""
- Kaggle 데이터를 사용하려면 kaggle API 토큰을 Codespaces에 업로드하고 환경변수 KAGGLE_CONFIG_DIR를 설정한 뒤 kaggle 명령어로 다운로드하세요.
- 예시:
  1) kaggle.json을 ~/.kaggle/kaggle.json으로 업로드
  2) !kaggle datasets download -d <dataset> --unzip
- 교육부/기상청 등 공식 데이터의 공개 엔드포인트로 교체하면 더욱 정확한 대시보드가 됩니다.
""")


