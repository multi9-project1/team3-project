# ⚠️ 중요 보안 경고

## 🚨 API 키가 노출되었습니다!

귀하의 API 키가 대화 중에 평문으로 노출되었습니다.
**즉시 다음 조치를 취하세요:**

---

## 📋 필수 조치 사항

### 1. OpenAI API 키 재발급 (즉시)


**재발급 절차:**
1. https://platform.openai.com/api-keys 접속
2. 노출된 키 삭제 (Revoke)
3. 새 키 생성
4. `.env` 파일 업데이트

---

### 2. Kakao API 키 확인

**현재 키:**

**확인 사항:**
- https://developers.kakao.com 접속
- API 사용량 모니터링
- 의심스러운 사용 내역 확인
- 필요시 키 재발급

---

## 🔒 보안 권장사항

### 1. API 키 관리

✅ **해야 할 것:**
- `.env` 파일에만 API 키 저장
- `.gitignore`에 `.env` 포함 확인
- API 키 절대 코드에 하드코딩 금지
- API 키 주기적으로 변경

❌ **하지 말아야 할 것:**
- API 키를 채팅/이메일로 공유
- API 키를 스크린샷으로 공유
- API 키를 Git에 커밋
- API 키를 공개 저장소에 업로드

### 2. Git 관리

**`.gitignore` 확인:**
```bash
# .gitignore에 포함되어 있는지 확인
cat .gitignore | grep .env
```

**결과:**
```
.env        # 이 줄이 있어야 함
```

### 3. 사용량 모니터링

**OpenAI:**
- https://platform.openai.com/usage
- 일일/월별 사용량 확인
- 예산 한도 설정 권장

**Kakao:**
- https://developers.kakao.com
- API 호출량 모니터링
- 무료 할당량 확인

---

## 🛡️ 즉시 조치 체크리스트

- [ ] OpenAI API 키 삭제 (Revoke)
- [ ] OpenAI 새 API 키 생성
- [ ] `.env` 파일에 새 키 업데이트
- [ ] Kakao API 사용량 확인
- [ ] `.gitignore`에 `.env` 포함 확인
- [ ] Git 커밋 전 `.env` 제외 확인

---

## 💡 안전한 사용 방법

### 로컬 개발
```bash
# .env 파일 생성
cp .env.example .env

# .env 파일 편집 (실제 API 키 입력)
nano .env

# Git 커밋 전 확인
git status
# .env 파일이 목록에 없어야 함!
```

### 배포
- 환경변수로 직접 설정
- Secret Manager 사용 (클라우드)
- `.env` 파일 절대 배포 서버에 업로드 금지

---

## 🔑 새 API 키 발급 후

### .env 파일 업데이트
```bash
# .env 파일 편집
nano .env

# OPENAI_API_KEY= 뒤에 새 키 입력
OPENAI_API_KEY=새로운_API_키_입력

# 저장 후 앱 재시작
streamlit run app.py
```

---

## 📞 문제 발생 시

### OpenAI API 키 도난 의심
1. https://platform.openai.com/api-keys
2. 모든 키 즉시 삭제 (Revoke)
3. 사용량 확인
4. 청구 내역 확인
5. 필요시 OpenAI 지원팀 연락

### Kakao API 오남용 의심
1. https://developers.kakao.com
2. API 사용 통계 확인
3. 의심스러운 호출 확인
4. 키 재발급

---

## ✅ 확인 완료 후

이 경고 메시지를 확인하고 조치를 완료했다면:
- [ ] OpenAI API 키 재발급 완료
- [ ] `.env` 파일 업데이트 완료
- [ ] 앱 정상 작동 확인
- [ ] `.gitignore` 설정 확인

**이 문서는 읽은 후 삭제하세요.**

---

**보안은 선택이 아닌 필수입니다!** 🔐
