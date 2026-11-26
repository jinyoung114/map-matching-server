import json
import importlib.util
import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch, MagicMock
from types import ModuleType

from services.eta_service import EtaService, OrderedRoute, timestamp_seconds


class EtaTests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parent / 'eta_linear_route.csv'
        self.model = OrderedRoute(path, ['A','B'], {'A':{'latitude':36,'longitude':127}, 'B':{'latitude':36,'longitude':127.0333}})
        self.clock = datetime(2026, 11, 25, tzinfo=timezone.utc).timestamp()

    def point(self, progress):
        return dict(edge_u=1, edge_v=2, fraction=progress/3000,lat=36,lon=127 + progress/3000*.0333,distance_to_road_m=0)

    def step(self, service, seconds, progress, **kwargs):
        stamp = datetime.fromtimestamp(self.clock+seconds, timezone.utc).isoformat()
        return service.update(self.point(progress), stamp, now=self.clock+seconds, **kwargs)

    def test_distance_speed_time_and_passed_stop(self):
        eta = EtaService(self.model)
        self.step(eta,0,0);self.step(eta,3,18)
        result=self.step(eta,6,36)
        self.assertEqual(result['status'],'estimated')
        self.assertEqual(result['speed_mps'],6)
        self.assertEqual(result['arrivals']['B']['eta_seconds'],494)
        self.assertNotIn('A',result['arrivals'])
        self.assertEqual(result['arrivals']['B']['stops_remaining'],1)

    def test_stale_and_simulation_are_explicit(self):
        stamp=datetime.fromtimestamp(self.clock,timezone.utc).isoformat()
        self.assertEqual(EtaService(self.model).update(self.point(0),stamp,now=self.clock+60)['status'],'stale')
        eta=EtaService(self.model,simulation=True)
        for i in range(3):
            result=eta.update(self.point(i*18),datetime.fromtimestamp(self.clock+i*3,timezone.utc).isoformat(),now=self.clock+1000+i)
        self.assertEqual(result['status'],'estimated')
        self.assertTrue(result['simulation'])
        self.assertEqual(result['updated_at'],int((self.clock+1002)*1000))

    def test_reversal_and_large_jump(self):
        eta=EtaService(self.model)
        for t,p in [(0,100),(3,118),(6,136)]:self.step(eta,t,p)
        self.assertEqual(self.step(eta,9,115)['status'],'direction_unknown')
        self.assertEqual(self.step(eta,12,90)['status'],'direction_unknown')
        other=EtaService(self.model)
        self.step(other,0,0)
        self.assertEqual(self.step(other,3,900)['status'],'position_jump')

    def test_stopped_out_of_order_and_unknown_edge(self):
        eta=EtaService(self.model)
        for t,p in [(0,0),(3,18),(6,36)]:self.step(eta,t,p)
        self.assertEqual(self.step(eta,6,36)['status'],'invalid_timestamp')
        for t in [9,12,15,18]:result=self.step(eta,t,36)
        self.assertEqual(result['status'],'stopped')
        point=self.point(50);point['edge_u']=999
        self.assertEqual(eta.update(point,datetime.fromtimestamp(self.clock+21,timezone.utc).isoformat(),now=self.clock+21)['status'],'off_route')

    def test_bus_states_are_independent(self):
        first,second=EtaService(self.model),EtaService(self.model)
        for t,p in [(0,0),(3,18),(6,36)]:result=self.step(first,t,p)
        self.assertEqual(result['status'],'estimated')
        self.assertEqual(self.step(second,6,36)['status'],'calculating')

    def test_reverse_edge_fraction_and_local_timestamp(self):
        point=self.point(900);point.update(edge_u=2,edge_v=1,fraction=.7)
        self.assertAlmostEqual(self.model.progress(point),900)
        self.assertEqual(timestamp_seconds('2026-11-25T09:00:00'),self.clock)

    def test_existing_routes_stop_order(self):
        data=Path(os.environ.get('ETA_TEST_DATA_DIR',Path(__file__).resolve().parents[1]/'data'))
        fixture=json.loads((Path(__file__).parent/'eta_catalog_fixture.json').read_text(encoding='utf-8'))
        for route_id,folder in [('route_001','아산역'),('route_002','천안터미널역')]:
            route=OrderedRoute(data/folder/'road_edges_bidirectional.csv',fixture['routes'][route_id],fixture['stops'])
            positions=[s['progress'] for s in route.stops]
            self.assertEqual(positions,sorted(positions))
            self.assertTrue(all(s['snap_distance_m']<=120 for s in route.stops))

    def test_delayed_live_gps_uses_measurement_time(self):
        eta = EtaService(self.model)
        self.step(eta, 0, 0)
        self.step(eta, 3, 18)
        stamp = datetime.fromtimestamp(self.clock + 6, timezone.utc).isoformat()
        result = eta.update(self.point(36), stamp, now=self.clock + 16)
        self.assertEqual(result['arrivals']['B']['estimated_arrival_at'], int((self.clock + 500) * 1000))

    def test_complete_ordered_traversal_of_both_routes(self):
        data=Path(os.environ.get('ETA_TEST_DATA_DIR',Path(__file__).resolve().parents[1]/'data'))
        fixture=json.loads((Path(__file__).parent/'eta_catalog_fixture.json').read_text(encoding='utf-8'))
        for route_id,folder in [('route_001','아산역'),('route_002','천안터미널역')]:
            route=OrderedRoute(data/folder/'road_edges_bidirectional.csv',fixture['routes'][route_id],fixture['stops'])
            eta=EtaService(route, simulation=True)
            segment_index=0
            predictions=0
            for step, progress in enumerate(range(0,int(route.length),18)):
                while segment_index+1<len(route.segments) and route.segments[segment_index+1]['start']<=progress:
                    segment_index+=1
                s=route.segments[segment_index]
                fraction=(progress-s['start'])/s['length']
                point=dict(edge_u=s['u'],edge_v=s['v'],fraction=fraction,
                           lat=s['lat1']+fraction*(s['lat2']-s['lat1']),
                           lon=s['lon1']+fraction*(s['lon2']-s['lon1']))
                stamp=datetime.fromtimestamp(self.clock+step*3,timezone.utc).isoformat()
                result=eta.update(point,stamp,now=self.clock+step*3)
                self.assertIn(result['status'],['calculating','estimated','completed'])
                if result['status']=='estimated':
                    predictions+=1
                    self.assertAlmostEqual(result['speed_mps'],6,places=1)
                    self.assertTrue(all(a['eta_seconds']>=0 for a in result['arrivals'].values()))
            self.assertGreater(predictions,100)


class EndpointTests(unittest.TestCase):
    setUp = EtaTests.setUp
    point = EtaTests.point

    @classmethod
    def setUpClass(cls):
        # Isolate unchanged native HMM dependencies. This tests orchestration,
        # not a real GPS replay or the availability of SciPy DLLs.
        road_module = ModuleType('src.road_network')
        road_module.RoadNetwork = MagicMock()
        match_module = ModuleType('services.map_matching_service')
        match_module.MapMatchingService = MagicMock()
        path=Path(__file__).resolve().parents[1]/'main.py'
        spec=importlib.util.spec_from_file_location('_eta_endpoint_test',path)
        cls.main=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'src.road_network':road_module,
                                    'services.map_matching_service':match_module,
                                    '_eta_endpoint_test':cls.main}):
            spec.loader.exec_module(cls.main)

    def test_request_body_schema_survives_serialization_wrapper(self):
        schema=self.main.app.openapi()
        self.assertIn('requestBody',schema['paths']['/mapmatch']['post'])
        self.assertIn('simulation',schema['components']['schemas']['TripRequest']['properties'])
    # Exercise lifecycle and payload integration without writing to Firebase.
    def test_endpoint_lifecycle_and_route_change(self):
        main = self.main
        fake=MagicMock()
        fake.process_gps.return_value={'matched':self.point(36),'current_node':2}
        with patch.object(main,'get_road_network',return_value=object()), patch.object(main,'MapMatchingService',return_value=fake), \
             patch.object(main,'get_eta_service',return_value=EtaService(self.model)), \
             patch.object(main,'start_bus_trip'),patch.object(main,'end_bus_trip') as end,patch.object(main,'update_bus_location') as write:
            main.start_trip(trip=main.TripRequest(bus_id='eta_test',route_id='route_001'))
            wrong=main.mapmatch(gps=main.GPSRequest(bus_id='eta_test',route_id='route_002',lat=36,lon=127,timestamp='2026-11-25T09:00:00'))
            self.assertEqual(wrong['status'],'error')
            self.assertFalse(fake.process_gps.called)
            result=main.mapmatch(gps=main.GPSRequest(bus_id='eta_test',route_id='route_001',lat=36,lon=127,timestamp='2026-11-25T09:00:00'))
            self.assertIn('eta',result)
            self.assertIn('eta',write.call_args.kwargs)
            main.end_trip(trip=main.TripRequest(bus_id='eta_test',route_id='route_001'))
            self.assertNotIn('eta_test',main.services)
            self.assertNotIn('eta_test',main.trip_routes)
            end.assert_called()

    def test_eta_failure_still_writes_bus_position(self):
        main=self.main
        fake=MagicMock()
        fake.process_gps.return_value={'matched':self.point(36),'current_node':2}
        main.services['eta_failure']=fake
        main.trip_routes['eta_failure']='route_001'
        try:
            with patch.object(main,'get_eta_service',side_effect=ValueError('invalid metadata')), \
                 patch.object(main,'update_bus_location') as write,patch.object(main.logger,'exception'):
                result=main.mapmatch(gps=main.GPSRequest(bus_id='eta_failure',route_id='route_001',lat=36,lon=127,timestamp='2026-11-25T09:00:00'))
                self.assertEqual(result['eta']['status'],'unavailable')
                self.assertEqual(write.call_args.kwargs['lat'],36)
        finally:
            main.services.pop('eta_failure',None)
            main.trip_routes.pop('eta_failure',None)

    def test_firebase_preserves_existing_fields(self):
        from services import firebase_service as service
        with patch.object(service,'initialize_firebase'),patch.object(service.db,'reference') as reference:
            service.update_bus_location('a','route_001',36,127,2,'timestamp',eta={'status':'calculating'})
            payload=reference.return_value.set.call_args.args[0]
            self.assertEqual(payload['lat'],36)
            self.assertTrue(payload['trip_active'])
            self.assertEqual(payload['eta']['status'],'calculating')


if __name__ == '__main__':
    unittest.main()
