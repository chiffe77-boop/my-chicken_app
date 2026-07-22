import streamlit as st
import requests
import pandas as pd
import re
from collections import Counter
import plotly.express as px
from wordcloud import WordCloud
from urllib.parse import urlparse, parse_qs

# =========================================================
# 기본 설정
# =========================================================
st.set_page_config(page_title="유튜브 댓글 분석기", page_icon="💬", layout="wide")

# 예시로 쓸 기본 링크 두 개
EXAMPLE_1_URL = "https://www.youtube.com/watch?v=fWb7VeBJSWs"
EXAMPLE_2_URL = "https://www.youtube.com/watch?v=6J6w5DBJAT0"


# =========================================================
# 유튜브 링크에서 영상 ID만 뽑아내는 함수
# - youtu.be/영상ID  형태
# - youtube.com/watch?v=영상ID  형태
# - 뒤에 si=xxxx 같은 부가 값이 붙어도 무시하고 영상 ID만 추출
# =========================================================
def extract_video_id(url: str):
    if not url:
        return None

    url = url.strip()
    parsed = urlparse(url)

    # 1) youtu.be 짧은 주소인 경우 -> 경로(path) 부분이 곧 영상 ID
    #    예: https://youtu.be/fWb7VeBJSWs?si=abcd123
    if "youtu.be" in parsed.netloc:
        video_id = parsed.path.lstrip("/")
        return video_id if video_id else None

    # 2) youtube.com/watch?v=영상ID 형태인 경우 -> 쿼리스트링에서 v 값 추출
    if "youtube.com" in parsed.netloc:
        query = parse_qs(parsed.query)
        if "v" in query:
            return query["v"][0]

        # 혹시 /shorts/영상ID 형태로 들어와도 대비해서 처리
        if "/shorts/" in parsed.path:
            return parsed.path.split("/shorts/")[-1].split("/")[0]

    # 위 형태에 해당하지 않으면 영상 ID를 찾지 못한 것으로 처리
    return None


# =========================================================
# YouTube Data API v3로 댓글을 가져오는 함수
# - part=snippet, order=relevance(좋아요 많은 순), 최대 100개
# =========================================================
def fetch_comments(video_id: str, api_key: str):
    url = "https://www.googleapis.com/youtube/v3/commentThreads"
    params = {
        "part": "snippet",
        "videoId": video_id,
        "order": "relevance",   # 최신순이 아니라 인기(좋아요 많은)순
        "maxResults": 100,
        "key": api_key,
    }

    response = requests.get(url, params=params, timeout=10)

    # 정상 응답이 아니면 에러로 처리 (댓글 사용 중지, 잘못된 영상ID, API키 오류 등)
    if response.status_code != 200:
        return None, response.status_code

    data = response.json()
    items = data.get("items", [])

    comments = []
    for item in items:
        snippet = item["snippet"]["topLevelComment"]["snippet"]
        comments.append({
            "댓글": snippet.get("textOriginal", ""),
            "좋아요": snippet.get("likeCount", 0),
        })

    return comments, 200


# =========================================================
# 댓글 목록에서 단어별 빈도수를 세는 함수
# - 한글/영문/숫자 등 '글자'를 기준으로 단어를 나눔 (특수문자, 이모지 등은 구분자로 취급)
# - 한 글자짜리 단어는 통계에서 제외
# - 단어 빈도 그래프(2단계)와 워드클라우드(3단계)에서 공통으로 사용
# =========================================================
def build_word_freq(comment_list):
    counter = Counter()

    for text in comment_list:
        # \w+ : 문자/숫자로 이루어진 덩어리를 단어로 인식 (한글도 포함됨)
        words = re.findall(r"\w+", text, flags=re.UNICODE)
        for word in words:
            if len(word) > 1:  # 한 글자짜리 단어는 제외
                counter[word] += 1

    return counter


def count_top_words(comment_list, top_n=20):
    return build_word_freq(comment_list).most_common(top_n)


# =========================================================
# 워드클라우드에 쓸 한글 폰트를 인터넷에서 내려받는 함수
# - 스트림릿 클라우드에는 한글 폰트가 기본으로 없어서, 미리 나눔고딕 폰트 파일을 받아둠
# - @st.cache_resource : 앱이 켜져있는 동안 한 번만 내려받고 재사용 (매번 다시 받지 않도록)
# =========================================================
FONT_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
FONT_PATH = "NanumGothic-Regular.ttf"

@st.cache_resource
def get_font_path():
    try:
        response = requests.get(FONT_URL, timeout=10)
        response.raise_for_status()  # 응답이 200이 아니면 에러 발생시킴

        with open(FONT_PATH, "wb") as f:
            f.write(response.content)

        return FONT_PATH
    except Exception:
        # 다운로드 실패 시 None을 돌려줘서, 호출하는 쪽에서 안내 메시지를 띄우게 함
        return None


# =========================================================
# 예시 버튼을 눌렀을 때 입력창 값을 바꿔주기 위한 콜백 함수들
# (버튼 클릭 -> session_state 값 변경 -> 입력창에 반영)
# =========================================================
def set_example_1():
    st.session_state["url_input"] = EXAMPLE_1_URL

def set_example_2():
    st.session_state["url_input"] = EXAMPLE_2_URL


# =========================================================
# 화면 구성 시작
# =========================================================
st.title("💬 유튜브 댓글 분석기 (1단계)")
st.caption("유튜브 영상 링크를 넣으면 인기 댓글을 최대 100개까지 가져와서 보여줘요.")

# 입력창에 처음 보여줄 기본값 설정 (한 번만 초기화)
if "url_input" not in st.session_state:
    st.session_state["url_input"] = EXAMPLE_1_URL

# 예시 버튼 두 개를 나란히 배치
col1, col2 = st.columns(2)
with col1:
    st.button("예시 1 · 흑백리뷰 커링클", on_click=set_example_1, use_container_width=True)
with col2:
    st.button("예시 2 · 잡식맨 커링클", on_click=set_example_2, use_container_width=True)

# 유튜브 링크 입력창 (기본값은 session_state에 저장된 값)
video_url = st.text_input("유튜브 영상 링크를 붙여넣어주세요", key="url_input")

# 분석 시작 버튼
analyze = st.button("댓글 가져오기 🔍", type="primary")

# =========================================================
# 버튼을 눌렀을 때 실제 동작
# =========================================================
if analyze:
    video_id = extract_video_id(video_url)

    if not video_id:
        st.error("😥 유튜브 링크에서 영상 정보를 찾을 수 없어요. 링크를 다시 확인해주세요.")
    else:
        # secrets.toml (또는 스트림릿 클라우드 Secrets 설정)에서 API 키 불러오기
        api_key = st.secrets.get("YOUTUBE_API_KEY")

        if not api_key:
            st.error("⚠️ YOUTUBE_API_KEY가 설정되어 있지 않아요. 스트림릿 클라우드의 Secrets 설정을 확인해주세요.")
        else:
            with st.spinner("댓글을 가져오는 중이에요..."):
                comments, status_code = fetch_comments(video_id, api_key)

            # 요청 자체가 실패한 경우 (잘못된 영상ID, 댓글 사용 중지, API 키 오류 등)
            if comments is None:
                if status_code == 403:
                    st.error("🚫 이 영상은 댓글이 꺼져있거나, API 키 권한/할당량 문제로 댓글을 가져올 수 없어요.")
                elif status_code == 404:
                    st.error("❓ 해당 영상을 찾을 수 없어요. 링크가 올바른지 확인해주세요.")
                else:
                    st.error(f"😥 댓글을 가져오지 못했어요. (에러 코드: {status_code}) 링크나 API 키를 확인해주세요.")

            # 요청은 성공했지만 댓글이 하나도 없는 경우
            elif len(comments) == 0:
                st.warning("📭 이 영상에는 아직 댓글이 없거나, 댓글을 가져올 수 없었어요.")

            # 정상적으로 댓글을 가져온 경우
            else:
                # 좋아요 많은 순으로 정렬
                df = pd.DataFrame(comments).sort_values(by="좋아요", ascending=False).reset_index(drop=True)

                # 가져온 댓글 개수를 큰 지표 카드로 표시
                st.metric(label="가져온 댓글 개수", value=f"{len(df)}개")

                # 댓글 표로 보여주기
                st.dataframe(df, use_container_width=True, hide_index=True)

                # -----------------------------------------------
                # 자주 나온 단어 TOP 20 그래프
                # -----------------------------------------------
                st.subheader("📊 자주 나온 단어 TOP 20")

                top_words = count_top_words(df["댓글"].tolist(), top_n=20)

                if not top_words:
                    st.info("분석할 단어가 없어요. (한 글자짜리 단어는 제외돼요)")
                else:
                    word_df = pd.DataFrame(top_words, columns=["단어", "빈도수"])

                    # 그래프에서 가장 많이 나온 단어가 위쪽에 오도록,
                    # 빈도수가 낮은 순으로 정렬해서 데이터를 넣어줌 (가로 막대그래프는 아래에서부터 쌓임)
                    word_df = word_df.sort_values(by="빈도수", ascending=True)

                    fig = px.bar(
                        word_df,
                        x="빈도수",
                        y="단어",
                        orientation="h",
                        text="빈도수",
                    )
                    fig.update_layout(
                        yaxis_title="",
                        xaxis_title="언급 횟수",
                        height=600,
                    )

                    st.plotly_chart(fig, use_container_width=True)

                # -----------------------------------------------
                # 워드클라우드 그림
                # -----------------------------------------------
                st.subheader("☁️ 댓글 워드클라우드")

                font_path = get_font_path()

                if font_path is None:
                    st.error("😥 한글 폰트를 내려받지 못해서 워드클라우드를 만들 수 없어요. 잠시 후 다시 시도해주세요.")
                else:
                    word_freq = build_word_freq(df["댓글"].tolist())

                    if not word_freq:
                        st.info("워드클라우드로 그릴 단어가 없어요. (한 글자짜리 단어는 제외돼요)")
                    else:
                        wordcloud = WordCloud(
                            font_path=font_path,
                            background_color="white",  # 배경 흰색
                            width=1000,
                            height=600,
                        ).generate_from_frequencies(word_freq)

                        # matplotlib 없이 바로 이미지(PIL Image)로 변환해서 화면에 띄움
                        wordcloud_image = wordcloud.to_image()
                        st.image(wordcloud_image, use_container_width=True)
