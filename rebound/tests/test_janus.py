import rebound
import unittest
import math
import rebound.data
import warnings

class TestIntegratorJanus(unittest.TestCase):
    def test_janus_energy(self):
        for o, eps in [ (2,1e-4), (4,1e-8), (6,1e-9), (8,1e-11), (10,1e-13)]:
            sim = rebound.Simulation()
            sim.add(m=1.)
            sim.add(m=1e-3,a=1.12313)
            sim.add(m=1e-3,a=2.32323)
            sim.move_to_com()
            sim.dt = 0.25
            sim.integrator = "janus"
            sim.ri_janus.order = o
            sim.ri_janus.scale_pos = 1e16
            sim.ri_janus.scale_vel = 1e16
            e0 = sim.calculate_energy()
            sim.integrate(1e2)
            e1 = sim.calculate_energy()
            self.assertLess(math.fabs((e0-e1)/e1),eps)
    
    def test_janus_reverse(self):
        for o in [2,4,6,8,10]:
            sim = rebound.Simulation()
            sim.add(m=1.)
            sim.add(m=1e-3,a=1.12313,omega=0.32643,l=0.3788,e=0.012)
            sim.add(m=1e-3,a=2.32323,omega=0.12314,l=0.1726,e=0.103)
            sim.move_to_com()
            sim.dt = 0.25
            sim.integrator = "janus"
            sim.ri_janus.order = o
            sim.ri_janus.safe_mode = 0
            sim.ri_janus.scale_pos = 1e16
            sim.ri_janus.scale_vel = 1e16

            sim.integrator_janus_to_int()
            x1, x2 = sim.particles[1].x, sim.particles[2].x


            sim.integrate(1e2,exact_finish_time=0)
            sim.dt *= -1
            sim.ri_janus.is_synchronized = 0
            sim.integrate(0,exact_finish_time=0)
            
            xf1, xf2 = sim.particles[1].x, sim.particles[2].x
            
            self.assertEqual(x1,xf1)
            self.assertEqual(x2,xf2)

if __name__ == "__main__":
    unittest.main()