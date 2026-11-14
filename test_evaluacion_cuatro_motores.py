import hashlib
import json
import unittest
from copy import deepcopy
from nba_evaluacion_cuatro_motores import evaluar_cuatro_motores


def ejemplo():
    reg = {'partido_id': '123', 'inicio_utc': '2026-11-14T20:00:00Z',
           'equipos': {'local': 'Denver Nuggets', 'visitante': 'New Orleans Pelicans'},
           'cuatro_motores': [
               {'modelo': 'Base', 'local': 100, 'visitante': 110, 'total': 210},
               {'modelo': 'Modelo C', 'local': 101, 'visitante': 109, 'total': 210},
               {'modelo': 'Ensemble', 'local': 102, 'visitante': 108, 'total': 210},
               {'modelo': 'Pace + Eficiencia', 'local': 103, 'visitante': 107, 'total': 210}]}
    def sellar(reg):
        canon = json.dumps(reg, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        return {'registro': reg, 'clave_unica': 'nba-consolidado-v1:123',
                'partido_id': '123', 'inicio_utc': reg['inicio_utc'],
                'creado_utc': '2026-11-14T19:00:00Z',
                'huella_sha256': hashlib.sha256(canon.encode()).hexdigest()}
    real = {'id': '123', 'fecha_utc': reg['inicio_utc'],
            'local': 'Denver Nuggets', 'visitante': 'New Orleans Pelicans',
            'finalizado': True, 'puntos_local': 105, 'puntos_visitante': 105}
    return reg, sellar, real


class EvaluacionTests(unittest.TestCase):
    def test_cuatro_motores(self):
        reg, sellar, real = ejemplo()
        r = evaluar_cuatro_motores([sellar(reg)], [real])
        self.assertEqual(r['partidos_evaluados'], 1)
        self.assertEqual(len(r['detalle']), 12)
        self.assertEqual(len(r['resumen']), 16)
        base_local = next(x for x in r['resumen'] if x['motor'] == 'Base' and x['objetivo'] == 'local')
        self.assertEqual(base_local['MAE'], 5)
        self.assertEqual(base_local['sesgo'], -5)

    def test_no_finalizado(self):
        reg, sellar, real = ejemplo()
        real['finalizado'] = False
        r = evaluar_cuatro_motores([sellar(reg)], [real])
        self.assertEqual(r['partidos_evaluados'], 0)
        self.assertEqual(r['descartes']['sin_resultado_final'], 1)

    def test_huella_alterada(self):
        reg, sellar, real = ejemplo()
        item = sellar(reg)
        item['registro']['cuatro_motores'][0]['local'] = 999
        r = evaluar_cuatro_motores([item], [real])
        self.assertEqual(r['descartes']['huella'], 1)

    def test_guardado_tardio(self):
        reg, sellar, real = ejemplo()
        item = sellar(reg)
        item['creado_utc'] = reg['inicio_utc']
        r = evaluar_cuatro_motores([item], [real])
        self.assertEqual(r['descartes']['registro_tardio'], 1)

    def test_modelo_incompleto(self):
        reg, sellar, real = ejemplo()
        reg['cuatro_motores'].pop()
        r = evaluar_cuatro_motores([sellar(reg)], [real])
        self.assertEqual(r['descartes']['cuatro_motores_incompletos'], 1)

    def test_total_incoherente(self):
        reg, sellar, real = ejemplo()
        reg['cuatro_motores'][0]['total'] = 999
        r = evaluar_cuatro_motores([sellar(reg)], [real])
        self.assertEqual(r['descartes']['datos_incompletos'], 1)

    def test_duplicado(self):
        reg, sellar, real = ejemplo()
        r = evaluar_cuatro_motores([sellar(reg), sellar(reg)], [real])
        self.assertEqual(r['partidos_evaluados'], 1)
        self.assertEqual(r['descartes']['duplicado'], 1)


if __name__ == '__main__':
    unittest.main()
