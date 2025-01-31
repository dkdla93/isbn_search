import streamlit as st
import pandas as pd
import requests
import urllib.parse
import time
import re
from io import BytesIO

# -----------------------------------------------------------------------------
# 공통: 네이버 검색 API 사용 함수
# -----------------------------------------------------------------------------
def extract_year(pubdate):
    """출간연도에서 첫 번째 4자리 연도만 추출"""
    if pd.isnull(pubdate):
        return ''
    pubdate = str(pubdate).strip()
    match = re.search(r'\d{4}', pubdate)
    if match:
        return match.group(0)
    return ''

@st.cache_data
def get_book_info_by_isbn13(isbn13, max_retries=5):
    """
    ISBN13으로 네이버 검색 API에서 정보를 조회하는 함수.
    반환값 예시:
      {
        'title': ...,
        'author': ...,
        'publisher': ...,
        'pubdate': ...,
        'price': ...,
        'isbn': ... (10, 13 혼합)
      }
    검색 실패 시 None 반환
    """
    url = "https://openapi.naver.com/v1/search/book.json"
    query = isbn13  # ISBN13 기반 검색
    headers = {
        'X-Naver-Client-Id': st.secrets["general"]["client_id"],
        'X-Naver-Client-Secret': st.secrets["general"]["client_secret"]
    }

    encoded_query = urllib.parse.quote(query)
    full_url = f"{url}?query={encoded_query}&display=1"  # 1개 결과만
    retries = 0

    while retries < max_retries:
        try:
            response = requests.get(full_url, headers=headers)
            if response.status_code == 200:
                data = response.json()
                items = data.get('items', [])
                if items:
                    item = items[0]  # 첫 번째 결과만 사용
                    return {
                        'title': item.get('title', '').replace('<b>', '').replace('</b>', '').strip(),
                        'author': item.get('author', '').strip(),
                        'publisher': item.get('publisher', '').strip(),
                        'pubdate': item.get('pubdate', '').strip(),
                        'price': item.get('price', '').strip(),
                        'isbn': item.get('isbn', '').strip()
                    }
                else:
                    return None
            elif response.status_code == 429:
                # Too Many Requests
                time.sleep(1)
                retries += 1
            else:
                return None
        except requests.exceptions.RequestException:
            return None
    
    return None


def get_isbn13_from_title_author_pub(title, author, publisher, pub_year, max_retries=5):
    """
    도서명, 저자, 출판사, 출간연도 정보를 활용해 네이버 검색 API로부터 ISBN13을 추출.
    기존 코드(기능1) 로직을 기반으로 함.
    """
    url = "https://openapi.naver.com/v1/search/book.json"
    headers = {
        'X-Naver-Client-Id': st.secrets["general"]["client_id"],
        'X-Naver-Client-Secret': st.secrets["general"]["client_secret"]
    }

    # 검색 쿼리 조합 (우선순위)
    query_combinations = [
        f"{title} {author} {publisher} {pub_year}",
        f"{title} {author}",
        f"{title} {publisher}",
        f"{title}"
    ]

    for query in query_combinations:
        encoded_query = urllib.parse.quote(query)
        full_url = f"{url}?query={encoded_query}&display=5"
        
        retries = 0
        while retries < max_retries:
            try:
                response = requests.get(full_url, headers=headers)
                if response.status_code == 200:
                    data = response.json()
                    items = data.get('items', [])
                    if items:
                        # 우선순위 쿼리에서 일치 항목 찾기
                        for item in items:
                            item_title = item.get('title', '').replace('<b>', '').replace('</b>', '').strip().lower()
                            item_author = item.get('author', '').strip().lower()
                            item_publisher = item.get('publisher', '').strip().lower()
                            item_pub_year = extract_year(item.get('pubdate', '').strip())
                            
                            # 모두 소문자로 변환해 비교
                            if (title.lower() in item_title) \
                               and (author.lower() in item_author) \
                               and (publisher.lower() in item_publisher) \
                               and (pub_year == item_pub_year):
                                # ISBN 추출
                                isbn_full = item.get('isbn', '')
                                isbn13 = extract_isbn13(isbn_full)
                                if isbn13:
                                    return isbn13
                        # 일치 항목 없으면, 첫 번째 결과의 ISBN 반환
                        first_item = items[0]
                        isbn_full = first_item.get('isbn', '')
                        isbn13 = extract_isbn13(isbn_full)
                        return isbn13
                    else:
                        # 검색 결과 없음
                        break
                elif response.status_code == 429:
                    time.sleep(1)
                    retries += 1
                else:
                    return None
            except requests.exceptions.RequestException:
                return None

    return None

def extract_isbn13(isbn_str):
    """
    네이버 API 반환값 isbn_str은
    'ISBN10 ISBN13' 형식일 수도 있고, 하나만 올 수도 있음.
    이 중에서 ISBN13만 추출해서 반환.
    """
    if not isbn_str:
        return None
    
    # 공백으로 구분되어 있다면 ISBN10 / ISBN13 구조일 확률이 높음
    parts = isbn_str.split()
    for p in parts:
        # 길이가 13자리이며, 숫자인지 확인
        # ISBN13은 978 혹은 979로 시작할 가능성이 큼 (규격상)
        if len(p) == 13 and p.isdigit():
            return p
    return None

# -----------------------------------------------------------------------------
# 기능 1: ISBN(10자리) -> ISBN13 변환 (엑셀 업로드 -> 변환 -> 다운로드)
# -----------------------------------------------------------------------------
def run_feature_1():
    st.subheader("기능 1: ISBN(10자리) -> ISBN(13자리) 변환")

    uploaded_file = st.file_uploader("엑셀 파일 업로드", type=["xlsx", "xls"])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)

        # 예시: 엑셀에 '도서명', '저자', '출판사', '출간연도', 'ISBN' 열이 있다고 가정
        required_columns = ['도서명', '저자', '출판사', '출간연도', 'ISBN']
        for col in required_columns:
            if col not in df.columns:
                st.error(f"필수 열이 누락되었습니다: {col}")
                return
        
        # ISBN을 ISBN13으로 업데이트
        isbn_cache = {}
        for idx, row in df.iterrows():
            title = str(row['도서명']).strip() if not pd.isnull(row['도서명']) else ''
            author = str(row['저자']).strip() if not pd.isnull(row['저자']) else ''
            publisher = str(row['출판사']).strip() if not pd.isnull(row['출판사']) else ''
            year = extract_year(row['출간연도'])
            
            if not title:
                # 도서명 없으면 스킵
                df.at[idx, 'ISBN'] = '도서명 없음'
                continue

            cache_key = (title, author, publisher, year)
            if cache_key in isbn_cache:
                isbn13 = isbn_cache[cache_key]
            else:
                isbn13 = get_isbn13_from_title_author_pub(title, author, publisher, year)
                isbn_cache[cache_key] = isbn13
            
            if isbn13:
                df.at[idx, 'ISBN'] = isbn13
            else:
                df.at[idx, 'ISBN'] = '정보 없음'

            time.sleep(0.2)  # API 호출 사이 딜레이

        # 변환된 결과 다운로드 버튼
        st.success("변환이 완료되었습니다. 아래 버튼을 눌러 다운로드하세요.")
        output = BytesIO()
        df.to_excel(output, index=False)
        st.download_button(
            label="ISBN 변환 결과 다운로드",
            data=output.getvalue(),
            file_name="도서목록_업데이트.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


# -----------------------------------------------------------------------------
# 기능 2: 기존 정보(ISBN10, ISBN13, 도서명, 출간일 등)와 실제 ISBN13 검색 결과 비교
# -----------------------------------------------------------------------------
def run_feature_2():
    st.subheader("기능 2: ISBN(13자리)로 검색된 정보와 원본 정보 비교")

    uploaded_file = st.file_uploader("검증을 위한 엑셀 파일 업로드", type=["xlsx", "xls"])
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)

        # 예시: 'ISBN10', 'ISBN13', '도서명', '출간일', '출판사', '저자', '정가' 열이 있다고 가정
        # 실제 엑셀 파일에 맞추어 수정하세요.
        required_columns = ['ISBN10', 'ISBN13', '도서명', '출간일', '출판사', '저자', '정가']
        for col in required_columns:
            if col not in df.columns:
                st.error(f"필수 열이 누락되었습니다: {col}")
                return

        # 비교 결과를 저장할 컬럼들 추가
        df['일치여부'] = ''
        df['불일치_항목'] = ''

        for idx, row in df.iterrows():
            original_isbn10 = str(row['ISBN10']).strip() if not pd.isnull(row['ISBN10']) else ''
            original_isbn13 = str(row['ISBN13']).strip() if not pd.isnull(row['ISBN13']) else ''
            original_title = str(row['도서명']).strip() if not pd.isnull(row['도서명']) else ''
            original_author = str(row['저자']).strip() if not pd.isnull(row['저자']) else ''
            original_publisher = str(row['출판사']).strip() if not pd.isnull(row['출판사']) else ''
            original_price = str(row['정가']).strip() if not pd.isnull(row['정가']) else ''
            original_pubdate = str(row['출간일']).strip() if not pd.isnull(row['출간일']) else ''

            # ISBN13으로 정보 검색
            if not original_isbn13 or len(original_isbn13) < 13:
                df.at[idx, '일치여부'] = '검색 불가(ISBN13 없음)'
                df.at[idx, '불일치_항목'] = 'ISBN13 미입력'
                continue

            # API 조회
            book_info = get_book_info_by_isbn13(original_isbn13)
            time.sleep(0.2)

            if not book_info:
                # 검색 결과 없음
                df.at[idx, '일치여부'] = '검색 실패'
                df.at[idx, '불일치_항목'] = '검색 결과 없음'
                continue
            
            # Naver API 결과 추출
            api_title = book_info['title'].lower()
            api_author = book_info['author'].lower()
            api_publisher = book_info['publisher'].lower()
            api_price = book_info['price']
            api_pubdate = extract_year(book_info['pubdate'])

            # 비교할 원본 정보 소문자 변환
            o_title = original_title.lower()
            o_author = original_author.lower()
            o_publisher = original_publisher.lower()
            o_price = original_price  # 가격은 소문자 변환 불필요
            o_pubdate = extract_year(original_pubdate)

            # 각 항목 비교
            mismatch_list = []
            if o_title and (o_title not in api_title and api_title not in o_title):
                mismatch_list.append('도서명')
            if o_author and (o_author not in api_author and api_author not in o_author):
                mismatch_list.append('저자')
            if o_publisher and (o_publisher not in api_publisher and api_publisher not in o_publisher):
                mismatch_list.append('출판사')
            # 출간일(연도) 비교
            if o_pubdate and (o_pubdate != api_pubdate):
                mismatch_list.append('출간연도')
            # 정가 비교(문자열로 단순 비교)
            if o_price and (o_price != api_price):
                mismatch_list.append('정가')

            if len(mismatch_list) == 0:
                df.at[idx, '일치여부'] = '일치'
            else:
                df.at[idx, '일치여부'] = '불일치'
                df.at[idx, '불일치_항목'] = ','.join(mismatch_list)

        # 결과 다운로드
        st.success("비교가 완료되었습니다. 아래 버튼을 눌러 결과 파일을 다운로드하세요.")
        output = BytesIO()
        df.to_excel(output, index=False)
        st.download_button(
            label="비교 결과 다운로드",
            data=output.getvalue(),
            file_name="도서목록_비교결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# -----------------------------------------------------------------------------
# Streamlit 메인 구조
# -----------------------------------------------------------------------------
def main():
    st.title("ISBN 검색/검증 도구")
    st.write("네이버 검색 API를 이용해 ISBN을 변환하고, 기존 정보와 실제 검색 결과를 비교합니다.")

    # 탭을 통해 두 기능을 분리
    tab1, tab2 = st.tabs(["기능 1: ISBN 변환", "기능 2: 정보 비교"])

    with tab1:
        run_feature_1()

    with tab2:
        run_feature_2()

if __name__ == "__main__":
    main()
