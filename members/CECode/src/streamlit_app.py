from pathlib import Path

import streamlit as st

from jeju_data_visualization import create_visualization, load_data

st.set_page_config(page_title="제주 여행 시각화", layout="wide")

BASE_DIR = Path(__file__).resolve().parent


@st.cache_data
def get_data():
    return load_data(BASE_DIR / "jeju_crawling_100.csv")


st.title("제주 여행 추천 프로젝트 시각화")
st.caption("제주 여행 추천 프로젝트에서 수집한 데이터를 시각화하여 인사이트를 제공한 화면")

df = get_data()

col1, col2, col3 = st.columns(3)
col1.metric("전체 장소 수", len(df))
col2.metric("카테고리 수", df["category"].nunique(dropna=True))
col3.metric("평균 평점", f"{df['rating'].dropna().mean():.2f}")

st.pyplot(create_visualization(df), use_container_width=True)

with st.expander("원본 데이터 미리보기"):
    st.dataframe(df.head(30), use_container_width=True)
