"""Connector unit tests use explicitly fake payloads; these are never stored as live vacancies."""
import unittest
from unittest.mock import patch
from pathlib import Path
import tempfile
from fastapi.testclient import TestClient
from backend.app import database,main as main_module
from backend.app.main import app
from backend.app.services import sources

class FakeResponse:
    def __init__(self,status,payload,headers=None):self.status_code=status;self._payload=payload;self.headers=headers or {};self.text=""
    def json(self):return self._payload

class FakeClient:
    def __init__(self,response):self.response=response;self.calls=[]
    async def __aenter__(self):return self
    async def __aexit__(self,*args):return False
    async def get(self,url,params=None):self.calls.append((url,params));return self.response

ROLE=[{"title":"Motion Graphics Designer","category":"primary","synonyms":["Motion Designer"],"keywords":{"titles":[],"skills":["After Effects","video editing"],"tools":[],"industries":[]},"search_keywords":["After Effects"]}]

class ConnectorTests(unittest.IsolatedAsyncioTestCase):
    async def test_remoteok_public_feed_normalizes_and_attributes_live_listing(self):
        payload=[{"legal":"fixture"},{"id":789,"position":"Motion Graphics Designer","company":"Fixture Co","location":"Worldwide","url":"https://remoteok.com/remote-jobs/789-fixture","apply_url":"https://example.invalid/apply","description":"After Effects","date":"2026-01-02","tags":["design"]}]
        client=FakeClient(FakeResponse(200,payload));previous=sources._REMOTEOK_CACHE;old_path=sources._REMOTEOK_CACHE_PATH;sources._REMOTEOK_CACHE={"at":0,"jobs":None,"http_status":None,"error":""}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                sources._REMOTEOK_CACHE_PATH=Path(tmp)/"remoteok.json"
                with patch.object(sources.httpx,"AsyncClient",return_value=client):jobs,report=await sources.search_remoteok(ROLE,["India"],True)
                self.assertEqual(len(jobs),1);self.assertEqual(jobs[0]["url"],"https://remoteok.com/remote-jobs/789-fixture")
                self.assertEqual(jobs[0]["external_application_url"],"https://example.invalid/apply")
                self.assertEqual(report["source"],"Remote OK public jobs feed");self.assertEqual(report["status"],"ok")
        finally:sources._REMOTEOK_CACHE=previous;sources._REMOTEOK_CACHE_PATH=old_path

    async def test_greenhouse_connector_normalizes_live_schema(self):
        # TEST FIXTURE only: schema shaped like Greenhouse's public API; invalid domain must not reach database.
        response=FakeResponse(200,{"jobs":[{"title":"Motion Graphics Designer","company_name":"Fixture Co","location":{"name":"Hyderabad, India"},"absolute_url":"https://example.invalid/fixture-gh","content":"<p>After Effects and video editing.</p>","first_published":"2026-01-02"}]})
        client=FakeClient(response)
        with patch.object(sources.httpx,"AsyncClient",return_value=client):
            jobs,report=await sources.search_greenhouse(ROLE,["Hyderabad, India"],False,["fixture"])
        self.assertEqual(report['boards'][0]['status'],'ok');self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0]['work_mode'],'Not specified');self.assertTrue(jobs[0]['url'].startswith('https://'))

    async def test_greenhouse_http_failure_is_not_reported_as_empty_success(self):
        client=FakeClient(FakeResponse(404,{}))
        with patch.object(sources.httpx,"AsyncClient",return_value=client):jobs,report=await sources.search_greenhouse(ROLE,boards=['bad-board'])
        self.assertEqual(jobs,[]);self.assertEqual(report['status'],'error');self.assertEqual(report['boards'][0]['http_status'],404)

    async def test_lever_connector_normalizes_public_site_schema(self):
        # TEST FIXTURE only: Lever's public postings API response shape.
        response=FakeResponse(200,[{"text":"Motion Designer","company":"Fixture Co","categories":{"location":"Hyderabad, India","commitment":"Full-time"},"hostedUrl":"https://example.invalid/fixture-lever","descriptionPlain":"Create motion graphics using After Effects.","createdAt":1760000000000}])
        client=FakeClient(response)
        with patch.object(sources.httpx,"AsyncClient",return_value=client):
            jobs,report=await sources.search_lever(ROLE,["India"],False,[{"identifier":"fixture"}])
        self.assertEqual(report['boards'][0]['status'],'ok');self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0]['company'],'Fixture Co');self.assertIn('Lever',jobs[0]['source'])

    async def test_arbeitnow_connector_handles_pagination_and_remote(self):
        # TEST FIXTURE only: never presented as a real job or persisted.
        response=FakeResponse(200,{"data":[{"title":"Motion Graphics Designer","company_name":"Fixture Co","location":"Hyderabad, India","remote":True,"url":"https://example.invalid/fixture-arbeitnow","description":"After Effects editing","created_at":1760000000,"tags":[]}],"links":{"next":None}})
        client=FakeClient(response)
        with patch.object(sources.httpx,"AsyncClient",return_value=client):
            jobs,report=await sources.search_arbeitnow(ROLE,["India"],True,max_pages=1)
        self.assertEqual(report['queries'][0]['status'],'ok');self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0]['work_mode'],'Remote')

    async def test_remotive_full_feed_single_call_cache_and_source_attribution(self):
        # TEST FIXTURE only: API payload shape; one request is made because publisher recommends <=4/day.
        response=FakeResponse(200,{"jobs":[{"title":"Motion Graphics Designer","company_name":"Fixture Co","candidate_required_location":"India","url":"https://example.invalid/fixture-remotive","description":"After Effects","publication_date":"2026-01-02"}]})
        client=FakeClient(response);previous=sources._remotive_cache;previous_path=sources._REMOTIVE_CACHE_PATH;sources._remotive_cache={"at":0,"jobs":None,"http_status":None,"error":""}
        with tempfile.TemporaryDirectory() as tmp:
          sources._REMOTIVE_CACHE_PATH=Path(tmp)/'cache.json'
          try:
            with patch.object(sources.httpx,"AsyncClient",return_value=client):
                jobs,report=await sources.search_remotive(ROLE,["India"],True)
                jobs2,report2=await sources.search_remotive(ROLE,["India"],True)
            self.assertEqual(len(jobs),1);self.assertEqual(len(jobs2),1);self.assertEqual(len(client.calls),1)
            self.assertEqual(report['source'],'Remotive public remote-jobs API');self.assertTrue(report2['queries'][0]['cache_hit'])
          finally:sources._remotive_cache=previous;sources._REMOTIVE_CACHE_PATH=previous_path

    async def test_jobicy_public_feed_normalizes_and_caches_live_listing(self):
        # TEST FIXTURE only: Jobicy public API schema; never persisted as a live job.
        response=FakeResponse(200,{"success":True,"jobs":[{"id":123,"jobTitle":"Motion Graphics Designer","companyName":"Fixture Co","jobGeo":"Anywhere","url":"https://jobicy.com/jobs/fixture-role","jobDescription":"<p>After Effects and video editing.</p>","pubDate":"2026-01-02","jobType":["Full-Time"],"salaryMin":90000,"salaryMax":100000,"salaryCurrency":"USD","salaryPeriod":"yearly","jobIndustry":["Creative & Design"],"jobLevel":"Senior"}]})
        client=FakeClient(response);previous=sources._jobicy_cache;previous_path=sources._JOBICY_CACHE_PATH;sources._jobicy_cache={"at":0,"jobs":None,"http_status":None,"error":""}
        with tempfile.TemporaryDirectory() as tmp:
            sources._JOBICY_CACHE_PATH=Path(tmp)/'jobicy.json'
            try:
                with patch.object(sources.httpx,"AsyncClient",return_value=client):
                    jobs,report=await sources.search_jobicy(ROLE,["India"],True)
                    jobs_cached,report_cached=await sources.search_jobicy(ROLE,["India"],True)
                self.assertEqual(len(client.calls),1);self.assertEqual(len(jobs),1);self.assertEqual(len(jobs_cached),1)
                self.assertEqual(jobs[0]['source'],'Jobicy public remote-jobs API');self.assertEqual(jobs[0]['url'],'https://jobicy.com/jobs/fixture-role')
                self.assertIn('USD',jobs[0]['salary']);self.assertEqual(report['queries'][0]['status'],'ok')
                self.assertTrue(report_cached['queries'][0]['cache_hit'])
            finally:sources._jobicy_cache=previous;sources._JOBICY_CACHE_PATH=previous_path

    async def test_adzuna_missing_credentials_and_result_mapping(self):
        jobs,report=await sources.search_adzuna(ROLE,app_id="",app_key="")
        self.assertEqual(jobs,[]);self.assertEqual(report['status'],'configuration_required')
        response=FakeResponse(200,{"results":[{"title":"Motion Graphics Designer","company":{"display_name":"Fixture Co"},"location":{"display_name":"Hyderabad, India"},"redirect_url":"https://example.invalid/fixture-adzuna","description":"After Effects","created":"2026-01-02","salary_min":1,"salary_max":2}]})
        client=FakeClient(response)
        with patch.object(sources.httpx,"AsyncClient",return_value=client):
            jobs,report=await sources.search_adzuna(ROLE,["India"],["in"],"id","key")
        self.assertEqual(report['queries'][0]['status'],'ok');self.assertEqual(len(jobs),1)
        self.assertEqual(jobs[0]['company'],'Fixture Co')

    async def test_board_discovery_parses_supported_public_url(self):
        self.assertEqual(sources.normalize_board_url('https://boards.greenhouse.io/acme')['provider'],'greenhouse')
        self.assertEqual(sources.normalize_board_url('https://jobs.lever.co/acme')['identifier'],'acme')
        with self.assertRaises(ValueError):sources.normalize_board_url('https://example.com/careers')

    async def test_unrelated_title_is_not_matched_from_description_alone(self):
        self.assertIsNone(sources._matched_role({"title":"Technical Curriculum Developer","description":"Background in UI/UX Designer workflows"},ROLE)[0])
        self.assertIsNone(sources._matched_role({"title":"Senior Game Designer","description":"Senior designer for game economy and systems"},ROLE)[0])
        marketing={"title":"Digital Marketing Manager","synonyms":["Digital Campaign Manager"],"keywords":{"skills":["creative campaigns","brand identity"]},"search_keywords":["creative campaigns","brand identity"]}
        self.assertIsNone(sources._matched_role({"title":"Solutions Architect - Digital Native Business","description":"Digital native customer enablement. Own deployment architecture."},[marketing])[0])
        project={"title":"Project Manager","synonyms":["Team Lead","Project Coordinator"],"keywords":{},"search_keywords":[]}
        self.assertIsNone(sources._matched_role({"title":"Solutions Engineer, AI Build Team","description":"Lead customer technical implementations."},[project])[0])
        client_role={"title":"Client Manager","synonyms":["Client Coordinator"],"keywords":{},"search_keywords":[]}
        self.assertIsNone(sources._matched_role({"title":"IT Systems Engineer, Client Platform Engineer","description":"Manage devices and tools for employees."},[client_role])[0])

    async def test_work_mode_does_not_infer_remote_from_incidental_description(self):
        self.assertEqual(sources._mode('Tel Aviv, Israel','Collaborate with distributed teams using modern tools.'),'Not specified')
        self.assertEqual(sources._mode('Tel Aviv, Israel','This is a fully remote position.'),'Remote')
        self.assertEqual(sources._mode('Office','',False),'Office')

    async def test_remote_location_filter_respects_explicit_country_restrictions(self):
        candidate=["Hyderabad, Telangana, India"]
        self.assertFalse(sources._location_match("Remote, France",candidate,True))
        self.assertFalse(sources._location_match("Remote - US Only",candidate,True))
        self.assertTrue(sources._location_match("Remote (Worldwide)",candidate,True))
        self.assertTrue(sources._location_match("Remote, India",candidate,True))

    async def test_cross_source_duplicate_is_deduplicated_but_distinct_locations_are_kept(self):
        jobs=[{"title":"Senior Designer","company":"GitLab","location":"Remote, France","url":"https://one.invalid"},{"title":"Senior Designer","company":"gitlab","location":"Remote","url":"https://two.invalid"},{"title":"Senior Designer","company":"GitLab","location":"Remote, India","url":"https://three.invalid"}]
        result=sources.deduplicate_listings(jobs)
        self.assertEqual([x['url'] for x in result],['https://one.invalid','https://three.invalid'])

    async def test_search_variants_include_titles_synonyms_and_role_keyword_combinations(self):
        values=sources.search_variants(ROLE)
        self.assertIn('Motion Graphics Designer',values);self.assertIn('Motion Designer',values)
        self.assertTrue(any(x.startswith('Motion Graphics Designer ') for x in values))

    async def test_discover_endpoint_persists_and_returns_source_url(self):
        # TEST FIXTURE only: isolated DB ensures this invalid URL is never mixed with live listings.
        with tempfile.TemporaryDirectory() as tmp:
            old_db=database.DB_PATH;database.DB_PATH=Path(tmp)/'connector.sqlite3';database.init_db()
            job={"title":"Motion Graphics Designer","company":"Fixture Co","location":"Hyderabad, India","url":"https://example.invalid/test-fixture","description":"After Effects","source":"TEST FIXTURE Greenhouse","posted_at":"2026-01-01","work_mode":"Office","matched_role":"Motion Graphics Designer"}
            observed=[]
            async def found(*args,**kwargs):
                observed.append({'locations':args[1],'allow_remote':args[2]})
                return [job],{"source":"TEST FIXTURE","status":"ok","checked":1,"boards":[]}
            async def empty(*args,**kwargs):return [],{"source":"TEST FIXTURE","status":"configuration_required","checked":0,"error":"Not configured","queries":[]}
            try:
                with patch.object(main_module,"search_greenhouse",found),patch.object(main_module,"search_lever",empty),patch.object(main_module,"search_arbeitnow",empty),patch.object(main_module,"search_remotive",empty),patch.object(main_module,"search_jobicy",empty),patch.object(main_module,"search_remoteok",empty),patch.object(main_module,"search_adzuna",empty),TestClient(app) as client:
                    cid=client.post('/api/candidates',json={'name':'Fixture Candidate'}).json()['id']
                    response=client.post(f'/api/candidates/{cid}/discover',json={'roles':[ROLE[0]],'location':'Hyderabad, India'})
                    self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['found'],1)
                    self.assertEqual(observed,[{'locations':[],'allow_remote':True}])
                    self.assertEqual(response.json()['jobs'][0]['url'],job['url'])
                    stored=client.get(f'/api/candidates/{cid}/jobs').json()
                    self.assertEqual(len(stored),1);self.assertEqual(stored[0]['source'],job['source'])
                    self.assertEqual(response.json()['source_report']['sources'][0]['source'],'TEST FIXTURE')
                    self.assertFalse(response.json()['source_report']['provider_location_filter'])
            finally:database.DB_PATH=old_db

if __name__=='__main__':unittest.main()
