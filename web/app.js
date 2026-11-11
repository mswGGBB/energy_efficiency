// 주소 결정
//  - compose / EC2: 같은 주소의 nginx 가 /predict 를 API 컨테이너로 넘겨 주므로 "/predict"
//  - 로컬 개발(화면 5500 포트 + python api/server.py 8000 포트): Flask 서버로 직접
//  - 다른 곳(예: Lambda 함수 URL)을 쓰려면 index.html 에서 window.API_URL 을 먼저 지정
const API_URL = window.API_URL || (location.port === "5500" ? "http://127.0.0.1:8000/predict" : "/predict");

// 입력칸 값을 숫자로. 비었거나 숫자가 아니면 NaN
function num(id) {
  const v = document.getElementById(id).value.trim();
  return v === "" ? NaN : Number(v);
}
let currentMode = 'simple';

function switchTab(mode) {
  currentMode = mode;
  const buttons = document.querySelectorAll('.tab-btn');
  buttons[0].classList.toggle('active', mode === 'simple');
  buttons[1].classList.toggle('active', mode === 'detail');

  document.getElementById('detailSection').style.display = mode === 'detail' ? 'block' : 'none';
}

document.getElementById('predictForm').addEventListener('submit', async function(e) {
  e.preventDefault();

  // 범위 검증 (7.7 ~ 157 평)
  const pyeongVal = num('area_pyeong');
  if (isNaN(pyeongVal) || pyeongVal < 7.7 || pyeongVal > 157) {
    alert("평수는 7.7평 ~ 157평 사이만 입력할 수 있습니다.");
    return;
  }

  // 1. 공통 9개 입력값
  let payload = {
    mode: currentMode,
    area_pyeong: pyeongVal,
    stories: num('stories'),
    state: document.getElementById('state').value,
    climate_zone: document.getElementById('climate_zone').value,
    building_type: document.getElementById('building_type').value,
    vintage: document.getElementById('vintage').value,
    cooling_type: document.getElementById('cooling_type').value,
    heating_type: document.getElementById('heating_type').value,
    heating_fuel: document.getElementById('heating_fuel').value
  };

  // 2. 상세 모드일 경우 나머지 18개 특성 포함 (총 27개)
  if (currentMode === 'detail') {
    payload = {
      ...payload,
      bedrooms: num('bedrooms'),
      occupants: num('occupants'),
      heating_setpoint_f: num('heating_setpoint_f'),
      cooling_setpoint_f: num('cooling_setpoint_f'),
      infiltration_ach50: num('infiltration_ach50'),
      wall_r: num('wall_r'),
      ceiling_r: num('ceiling_r'),
      roof_r: num('roof_r'),
      floor_r: num('floor_r'),
      wall_type: document.getElementById('wall_type').value,
      windows: document.getElementById('windows').value,
      wall_area_ft2: num('wall_area_ft2'),
      window_area_ft2: num('window_area_ft2'),
      roof_area_ft2: num('roof_area_ft2'),
      door_area_ft2: num('door_area_ft2'),
      foundation: document.getElementById('foundation').value,
      attic: document.getElementById('attic').value,
      garage: document.getElementById('garage').value
    };
  }

  // 숫자칸이 비었거나 숫자가 아니면 서버로 보내지 않고 알려줌
  const bad = Object.entries(payload).filter(([k, v]) => typeof v === 'number' && isNaN(v)).map(([k]) => k);
  if (bad.length > 0) {
    alert("숫자를 입력해주세요: " + bad.join(", "));
    return;
  }

  const resultBox = document.getElementById('result');
  const warningBox = document.getElementById('warningBox');
  warningBox.style.display = 'none';

  document.getElementById('heatingKwh').innerText = "계산 중...";
  document.getElementById('coolingKwh').innerText = "계산 중...";
  resultBox.style.display = 'block';

  try {
    const response = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });

    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || `서버 오류 (${response.status})`);
    }

    // 결과 수치 표기 (kWh / MBtu)
    const heatKwh = data.heating_kwh_per_year ?? data.heating_kwh ?? 0;
    const coolKwh = data.cooling_kwh_per_year ?? data.cooling_kwh ?? 0;
    const heatMbtu = data.heating_mbtu_per_year ?? (heatKwh / 293.07).toFixed(1);
    const coolMbtu = data.cooling_mbtu_per_year ?? (coolKwh / 293.07).toFixed(1);

    document.getElementById('heatingKwh').innerText = Number(heatKwh).toLocaleString();
    document.getElementById('heatingMbtu').innerText = `(${heatMbtu} MBtu)`;

    document.getElementById('coolingKwh').innerText = Number(coolKwh).toLocaleString();
    document.getElementById('coolingMbtu').innerText = `(${coolMbtu} MBtu)`;

    // 경고 문구 처리
    if (data.warnings && data.warnings.length > 0) {
      warningBox.innerText = "⚠️ 경고: " + data.warnings.join(", ");
      warningBox.style.display = 'block';
    }

    // 캡처·비교용: 어떤 모델(v1/v2)이 답했는지, 검증 점수, 요청번호(request_id)를 함께 표시
    const r2 = data.validation_r2 ? ` · 검증 R² 난방 ${data.validation_r2.heating} / 냉방 ${data.validation_r2.cooling}` : '';
    const tag = data.model_tag ? ` · 모델 ${data.model_tag}` : '';
    const rid = data.request_id ? ` · 요청번호 ${data.request_id}` : '';
    document.getElementById('noteText').innerText = `적용 모델: ResStock ${currentMode.toUpperCase()}${tag}${r2}${rid} (단위: 연간 에너지 부하)`;

  } catch (error) {
    alert("예측 요청 실패: " + error.message);
    document.getElementById('heatingKwh').innerText = "에러";
    document.getElementById('coolingKwh').innerText = "에러";
  }
});