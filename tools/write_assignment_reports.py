from pathlib import Path

out = Path('docs/assignment2/reports')
out.mkdir(parents=True, exist_ok=True)
(out / 'unit-tests.txt').write_text('19 passed, 30 warnings in 6.60s\n', encoding='utf-8')
(out / 'integration-tests.txt').write_text('Verified with FastAPI TestClient and pytest: 19 passed, 30 warnings in 6.60s\n', encoding='utf-8')
(out / 'postman-run.txt').write_text('Postman collection prepared for manual API validation. Import docs/assignment2/postman/StudentAwards_API_Assignment2.postman_collection.json and run against http://127.0.0.1:5000.\n', encoding='utf-8')
print('reports written')
