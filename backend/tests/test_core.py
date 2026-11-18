import io, json, tempfile, unittest
from pathlib import Path
from docx import Document
from fastapi.testclient import TestClient
from backend.app import database
from backend.app import main as main_module
from backend.app.main import app
from backend.app.services.resume import parse_resume
from backend.app.services.intelligence import fallback_observed_roles, match_job, parse_role_json, classify_role
from backend.app.services.sources import _is_unrestricted_remote
from backend.app.services.eligibility import evaluate_eligibility

class CoreTests(unittest.TestCase):
    def test_eligibility_keeps_unknown_work_authorization_and_remote_region_explicit(self):
        profile={'location':'Hyderabad, India','experience_years':4}
        prefs={'remote_countries':['India'],'employment_types':['Full-time'],'experience_levels':['Mid-level']}
        job={'title':'Product Designer','location':'Remote - US only','work_mode':'Remote','employment_type':'Full-time','description':'','expired':False}
        result=evaluate_eligibility(profile,prefs,job)
        self.assertEqual(result['checks']['location'],'ineligible')
        self.assertEqual(result['checks']['work_authorization'],'unknown')
        self.assertEqual(result['status'],'ineligible')

    def test_automation_stop_and_config_are_scoped_to_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path=database.DB_PATH;database.DB_PATH=Path(tmp)/'auto.sqlite3';database.init_db()
            try:
                with TestClient(app) as client:
                    cid=client.post('/api/candidates',json={'name':'Fixture'}).json()['id']
                    with database.connect() as db:db.execute("INSERT INTO jobs(candidate_id,title,company,url,eligibility_status,match_score) VALUES(?,?,?,?,?,?)",(cid,'Fixture role','Fixture Co','https://example.invalid/apply','eligible',90))
                    start=client.post(f'/api/candidates/{cid}/automation/start',json={})
                    self.assertEqual(start.status_code,200,start.text)
                    self.assertEqual(start.json()['mode'],'dry_run')
                    self.assertTrue(client.post(f'/api/candidates/{cid}/automation/stop').json()['stopped'])
                    state=client.get(f'/api/candidates/{cid}/automation').json()
                    self.assertEqual(state['runs'][0]['status'],'stopped')
            finally:database.DB_PATH=old_path

    def test_production_authentication_csrf_and_candidate_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path=database.DB_PATH;old_auth=main_module.AUTH_ENABLED
            database.DB_PATH=Path(tmp)/'auth.sqlite3';database.init_db();main_module.AUTH_ENABLED=True
            try:
                with TestClient(app) as anon:
                    self.assertEqual(anon.get('/api/candidates').status_code,401)
                    one=TestClient(app);two=TestClient(app)
                    try:
                        r1=one.post('/api/auth/register',json={'email':'one@example.com','name':'One','password':'A-long-test-password-1'})
                        r2=two.post('/api/auth/register',json={'email':'two@example.com','name':'Two','password':'A-long-test-password-2'})
                        self.assertEqual(r1.status_code,200,r1.text);self.assertEqual(r2.status_code,200,r2.text)
                        csrf=one.cookies.get('jobpilot_csrf')
                        c1_response=one.post('/api/candidates',json={'name':'Private candidate'},headers={'X-CSRF-Token':csrf})
                        self.assertEqual(c1_response.status_code,200,c1_response.text)
                        c1=c1_response.json()['id']
                        self.assertEqual(two.get(f'/api/candidates/{c1}').status_code,404)
                        self.assertEqual(one.post('/api/candidates',json={'name':'No CSRF'}).status_code,403)
                        self.assertEqual(one.post('/api/candidates',json={'name':'CSRF OK'},headers={'X-CSRF-Token':csrf}).status_code,200)
                        self.assertEqual(one.post('/api/auth/logout',headers={'X-CSRF-Token':csrf}).status_code,200)
                        self.assertEqual(one.get('/api/candidates').status_code,401)
                    finally:
                        one.close();two.close()
            finally:
                main_module.AUTH_ENABLED=old_auth;database.DB_PATH=old_path

    def test_resume_extract_preserves_sections_and_missing_values(self):
        p=parse_resume("Sam Example\nsam@example.com\n\nSkills\nPython, SQL\n\nExperience\nAnalyst at Acme", "resume.docx")
        self.assertEqual(p['name'],'Sam Example')
        self.assertEqual(p['email'],'sam@example.com')
        self.assertTrue(any('Analyst' in x for x in p['experience']))
        self.assertEqual(p['phone'],'')

    def test_model_unavailable_fallback_never_invents_job_titles(self):
        p={'summary':'Python developer with SQL analytics experience','skills':['Python','SQL'],'experience':['Built data reports']}
        self.assertEqual(fallback_observed_roles(p),[])
        p['role_titles']=['Data Analyst']
        roles=fallback_observed_roles(p)
        self.assertEqual([r['title'] for r in roles],['Data Analyst'])
        self.assertEqual(roles[0]['category'],'primary')
        result=match_job(p,{'title':'Python Developer','description':'Python SQL developer'})
        self.assertGreater(result['score'],0)
        self.assertLessEqual(result['score'],100)
        numeric_scores=[v for v in result['component_scores'].values() if v is not None]
        self.assertLessEqual(max(numeric_scores),100)
        self.assertIsNone(result['component_scores']['portfolio_relevance'])

    def test_remote_location_filter_rejects_region_limited_remote_roles(self):
        self.assertFalse(_is_unrestricted_remote('US: SF, NYC, Seattle and Remote',True))
        self.assertFalse(_is_unrestricted_remote('Canada Remote',True))
        self.assertTrue(_is_unrestricted_remote('Remote (India)',True))
        self.assertFalse(_is_unrestricted_remote('Remote (India)',False))

    def test_match_score_penalizes_remote_listing_with_foreign_region(self):
        profile={'location':'Hyderabad, Telangana, India','skills':['Graphic Design'],'role_titles':['Graphic Designer'],'headline':'Graphic Designer','experience':['Created graphic assets'],'education':['Design Diploma']}
        local=match_job(profile,{'title':'Graphic Designer','matched_role':'Graphic Designer','location':'India','work_mode':'Remote','description':'Graphic design role.'})
        regional=match_job(profile,{'title':'Graphic Designer','matched_role':'Graphic Designer','location':'Remote - California','work_mode':'Remote','description':'Graphic design role.'})
        self.assertGreater(local['score'],regional['score'])
        self.assertIn('confirm',regional['eligibility_note'])

    def test_model_output_repair_recovers_structured_json_without_inventing_fields(self):
        parsed=parse_role_json('{roles:[{title:"Graphic Designer",category:"primary",evidence_terms:["Graphic Designer"],}],}')
        self.assertEqual(parsed['roles'][0]['title'],'Graphic Designer')
        self.assertEqual(parsed['roles'][0]['evidence_terms'],['Graphic Designer'])

    def test_role_categories_follow_resume_titles_and_skill_evidence(self):
        profile={'headline':'Senior Creative Designer | UI/UX','role_titles':['Creative Designer','Motion Graphics Designer'],'skills':['Project Management','UI Design','UX Design']}
        self.assertEqual(classify_role('Senior Creative Designer',profile),'primary')
        self.assertEqual(classify_role('Creative Director',profile),'related')
        self.assertEqual(classify_role('Project Manager',profile),'adjacent')

    def test_stats_counts_only_current_discovery_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path=database.DB_PATH; database.DB_PATH=Path(tmp)/'stats.sqlite3'; database.init_db()
            try:
                with database.connect() as db:
                    cid=db.execute("INSERT INTO candidates(name) VALUES('Test')").lastrowid
                    old_run=db.execute("INSERT INTO source_runs(candidate_id,query_json,report_json) VALUES(?,?,?)",(cid,'{}','{}')).lastrowid
                    new_run=db.execute("INSERT INTO source_runs(candidate_id,query_json,report_json) VALUES(?,?,?)",(cid,'{}','{}')).lastrowid
                    for title,run in [('Stale listing',old_run),('Current listing',new_run)]:
                        db.execute("INSERT INTO jobs(candidate_id,title,company,location,url,description,source,last_seen_run_id) VALUES(?,?,?,?,?,?,?,?)",(cid,title,'Fixture','Remote',f'https://example.invalid/{title.replace(" ", "-")}','test','TEST FIXTURE',run))
                self.assertEqual(main_module.stats(cid,user_id=None)['jobs'],1)
            finally:
                database.DB_PATH=old_path

    def test_role_endpoint_reuses_map_that_was_used_for_latest_search(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path=database.DB_PATH; database.DB_PATH=Path(tmp)/'roles.sqlite3'; database.init_db()
            role={'title':'Graphic Designer','category':'primary','confidence':0.9,'why':'Resume title','evidence_terms':['Graphic Designer'],'synonyms':['Visual Designer'],'keywords':{'titles':['Visual Designer']},'search_terms':['Graphic Designer','Visual Designer']}
            try:
                with database.connect() as db:
                    cid=db.execute("INSERT INTO candidates(name,resume_path,profile_json) VALUES(?,?,?)",('Test Candidate','resume.pdf','{}')).lastrowid
                    db.execute("INSERT INTO role_maps(candidate_id,model,roles_json) VALUES(?,?,?)",(cid,'qwen2.5:3b',json.dumps([role])))
                with TestClient(app) as client:
                    response=client.get(f'/api/candidates/{cid}/roles')
                    self.assertEqual(response.status_code,200,response.text)
                    self.assertEqual(response.json()['mode'],'stored')
                    self.assertEqual(response.json()['roles'][0]['title'],'Graphic Designer')
            finally:
                database.DB_PATH=old_path

    def test_candidate_upload_scoping_duplicates_and_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path=database.DB_PATH; database.DB_PATH=Path(tmp)/'test.sqlite3'
            old_uploads,old_generated=database.UPLOADS,database.GENERATED
            database.UPLOADS=Path(tmp)/'uploads'; database.UPLOADS.mkdir()
            database.GENERATED=Path(tmp)/'generated'; database.GENERATED.mkdir()
            old_main_uploads,old_main_generated=main_module.UPLOADS,main_module.GENERATED
            main_module.UPLOADS,main_module.GENERATED=database.UPLOADS,database.GENERATED
            database.init_db()
            try:
                with TestClient(app) as client:
                    c=client.post('/api/candidates',json={'name':'Test Candidate'}).json()['id']
                    d=Document(); d.add_paragraph('Alex Example'); d.add_paragraph('alex@example.com'); d.add_heading('Skills',level=1); d.add_paragraph('Figma, UX design')
                    stream=io.BytesIO(); d.save(stream)
                    up=client.post(f'/api/candidates/{c}/resume',files={'file':('candidate-'+'x'*180+'.docx',stream.getvalue(),'application/vnd.openxmlformats-officedocument.wordprocessingml.document')})
                    self.assertEqual(up.status_code,200,up.text)
                    self.assertTrue(up.json()['filename'].endswith('.docx'))
                    profile=client.get(f'/api/candidates/{c}').json()
                    self.assertEqual(profile['name'],'Alex Example')
                    self.assertEqual(profile['email'],'alex@example.com')
                    # Insert a genuine-shaped test fixture explicitly labelled only in this test.
                    with database.connect() as db:
                        cur=db.execute("INSERT INTO jobs(candidate_id,title,company,location,url,description,source) VALUES(?,?,?,?,?,?,?)",(c,'Designer','Test fixture','Remote','https://example.invalid/test','Figma design','TEST FIXTURE'))
                        jid=cur.lastrowid
                    first=client.post(f'/api/candidates/{c}/applications',json={'job_id':jid,'status':'Matched','match_score':80})
                    duplicate=client.post(f'/api/candidates/{c}/applications',json={'job_id':jid})
                    self.assertEqual(first.status_code,200)
                    self.assertEqual(duplicate.status_code,409)
                    generated=client.post(f'/api/candidates/{c}/documents/{jid}',json={})
                    self.assertEqual(generated.status_code,200,generated.text)
                    self.assertTrue((database.GENERATED / generated.json()['filename']).exists())
                    self.assertTrue((database.GENERATED / generated.json()['pdf_url'].rsplit('/',1)[1]).exists())
            finally:
                database.DB_PATH=old_path
                database.UPLOADS, database.GENERATED=old_uploads,old_generated
                main_module.UPLOADS,main_module.GENERATED=old_main_uploads,old_main_generated

if __name__=='__main__': unittest.main()
