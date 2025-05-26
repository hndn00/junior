function openModal() {
    document.getElementById('overlay').style.display = 'block';
    document.getElementById('modal').style.display = 'block';
}

function closeModal() {
    document.getElementById('overlay').style.display = 'none';
    document.getElementById('modal').style.display = 'none';
    document.getElementById('new_url').value = '';
}

let subjectCount = 0;

document.addEventListener('DOMContentLoaded', function() {
    if (document.querySelectorAll('#subjects .subject-item').length === 0) {
        addSubject(null); // 초기 아이템 추가
    }
});

function updateSliderValue(spanId, value) {
    const spanElement = document.getElementById(spanId);
    if (spanElement) {
        spanElement.innerText = value;
    }
}

function addSubject(afterElement, subjectName = '') {
    subjectCount++;
    const subjectItemId = `subjectItem${subjectCount}`;
    const nameId        = `name${subjectCount}`;
    const majorId       = `major${subjectCount}`;
    const weightId      = `weight${subjectCount}`;
    const sliderValueId = `sliderValue${subjectCount}`;

    const div = document.createElement('div');
    div.classList.add('subject-item');
    div.id = subjectItemId;

    div.innerHTML = `
    <div class="subject-inputs">
      <label for="${nameId}">Subject:</label>
      <input type="text" id="${nameId}" name="name" value="${subjectName}" required>

      <label for="${majorId}">Major Course:</label>
      <input type="checkbox" id="${majorId}" name="major" class="toggle-btn">

      <label for="${weightId}">Importance Level:</label>
      <input type="range" id="${weightId}" name="weight" min="0" max="100" step="1" value="50"
             oninput="updateSliderValue('${sliderValueId}', this.value)">
      <span id="${sliderValueId}">50</span>
    </div>
    <div class="subject-actions-container">
      <div class="action-left">
        <button type="button" class="remove-btn" onclick="removeSubject('${subjectItemId}')">🗑️ Delete</button>
      </div>
      <div class="action-right">
        <button type="button" class="add-below-btn" onclick="addSubject(this.closest('.subject-item'))">+ Add Subject</button>
      </div>
    </div>
  `;

    const subjectsDiv = document.getElementById('subjects');
    if (afterElement) {
        afterElement.parentNode.insertBefore(div, afterElement.nextSibling);
    } else {
        subjectsDiv.appendChild(div);
    }
}

function removeSubject(subjectItemId) {
    const subjectItemToRemove = document.getElementById(subjectItemId);
    const subjectsDiv = document.getElementById('subjects');
    if (!subjectItemToRemove) return;
    if (subjectsDiv.getElementsByClassName('subject-item').length > 1) {
        subjectItemToRemove.remove();
    } else {
        alert('At least one subject must remain.');
    }
}

function submitTimetableUrl() {
    const timetableUrl = document.getElementById('new_url').value;
    if (!timetableUrl) {
        alert('URL을 입력해주세요.');
        return;
    }
    const formData = new FormData();
    formData.append('new_url', timetableUrl);

    fetch('/process_timetable', {
        method: 'POST',
        body: formData
    })
        .then(response => {
            if (!response.ok) {
                return response.json().then(errData => {
                    throw new Error(errData.error || `서버 오류: ${response.status}`);
                }).catch(() => {
                    throw new Error(`서버 응답 오류: ${response.status}`);
                });
            }
            return response.json();
        })
        .then(data => {
            console.log('서버 응답:', data);
            if (data.error) {
                alert('시간표 로딩 오류: ' + data.error);
            }
            else if (Array.isArray(data.timetable_slots)) {
                // ← 이 한 줄을 추가했습니다!
                document.getElementById('timetable_slots').value = JSON.stringify(data.timetable_slots);

                populateSubjectsFromTimetable(data.timetable_slots);
                closeModal();

                if (data.timetable_slots.length > 0) {
                    alert('시간표를 성공적으로 불러왔습니다!');
                } else if (data.message) {
                    alert(data.message);
                } else {
                    alert('시간표는 불러왔으나, 포함된 과목이 없습니다.');
                }
            }
            else {
                alert('시간표 데이터를 불러오지 못했거나, 형식이 올바르지 않습니다.');
            }
        })
        .catch(error => {
            console.error('시간표 처리 중 오류 발생:', error);
            alert('시간표 처리 중 오류가 발생했습니다: ' + error.message);
        });
}

function populateSubjectsFromTimetable(slots) {
    const subjectsDiv = document.getElementById('subjects');
    subjectsDiv.innerHTML = '';
    subjectCount = 0;

    const uniqueSubjects = new Set();
    if (Array.isArray(slots)) {
        slots.forEach(slot => {
            if (slot && slot.length > 1 && slot[0] === '수업'
                && typeof slot[1] === 'string' && slot[1].trim()) {
                uniqueSubjects.add(slot[1].trim());
            }
        });
    }

    uniqueSubjects.forEach(subjectName => {
        addSubject(null, subjectName);
    });

    if (subjectsDiv.children.length === 0) {
        addSubject(null);
    }
}
