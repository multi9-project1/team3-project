from pathlib import Path
import warnings

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


warnings.filterwarnings("ignore")

BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "jeju_crawling_100.csv"


def configure_matplotlib() -> None:
    plt.rc("font", family="Malgun Gothic")
    plt.rc("axes", unicode_minus=False)


def load_data(csv_path: Path = DATA_PATH) -> pd.DataFrame:
    df = pd.read_csv(csv_path, encoding="cp949")
    df = df.rename(
        columns={
            "place_name": "name",
            "x": "lng",
            "y": "lat",
            "address_name": "address",
            "category_group_name": "category",
        }
    )

    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lng"] = pd.to_numeric(df["lng"], errors="coerce")
    df["total_cnt"] = pd.to_numeric(df["total_cnt"], errors="coerce").fillna(0)

    return df.dropna(subset=["lat", "lng"]).copy()


def create_visualization(df: pd.DataFrame):
    configure_matplotlib()
    fig, axes = plt.subplots(2, 2, figsize=(18, 12))
    fig.suptitle("제주 여행 추천 프로젝트 데이터 시각화", fontsize=20, fontweight="bold")

    order = df["category"].fillna("기타").value_counts().index

    sns.countplot(
        data=df.fillna({"category": "기타"}),
        x="category",
        order=order,
        hue="category",
        palette="Set2",
        ax=axes[0, 0],
        legend=False,
    )
    axes[0, 0].set_title("카테고리별 장소 수", fontsize=14)
    axes[0, 0].set_xlabel("카테고리")
    axes[0, 0].set_ylabel("장소 수")
    axes[0, 0].tick_params(axis="x", rotation=20)

    sns.histplot(df["rating"].dropna(), bins=15, kde=True, color="skyblue", ax=axes[0, 1])
    axes[0, 1].set_title("평점 분포", fontsize=14)
    axes[0, 1].set_xlabel("평점")
    axes[0, 1].set_ylabel("빈도")

    sns.scatterplot(
        data=df.fillna({"category": "기타"}),
        x="lng",
        y="lat",
        hue="category",
        size="rating",
        sizes=(20, 200),
        alpha=0.7,
        palette="tab10",
        ax=axes[1, 0],
    )
    axes[1, 0].set_title("제주 장소 위치 분포", fontsize=14)
    axes[1, 0].set_xlabel("경도")
    axes[1, 0].set_ylabel("위도")
    axes[1, 0].legend(loc="upper right", fontsize=8)

    sns.scatterplot(
        data=df.fillna({"category": "기타"}),
        x="total_cnt",
        y="rating",
        hue="category",
        alpha=0.7,
        palette="Set1",
        ax=axes[1, 1],
    )
    axes[1, 1].set_title("리뷰 수와 평점의 관계", fontsize=14)
    axes[1, 1].set_xlabel("리뷰 수")
    axes[1, 1].set_ylabel("평점")
    axes[1, 1].legend(loc="lower right", fontsize=8)

    plt.tight_layout(rect=[0, 0, 1, 0.96])
    return fig


def main() -> None:
    df = load_data()
    fig = create_visualization(df)
    plt.show()
    plt.close(fig)


if __name__ == "__main__":
    main()
