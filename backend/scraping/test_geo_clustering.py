import unittest
from scraping.geo_clustering import compute_anchor_clusters


def city(name, lat, lon, **extra):
    return {"name": name, "latitude": lat, "longitude": lon, **extra}


class TestComputeAnchorClusters(unittest.TestCase):
    def test_single_cluster_when_all_within_radius(self):
        cities = [
            city("Longueuil", 45.5369, -73.5105),
            city("Saint-Bruno-de-Montarville", 45.5333, -73.3500),
            city("Brossard", 45.4600, -73.4700),
        ]
        clusters = compute_anchor_clusters(cities, radius_km=80)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0].members), 3)

    def test_distant_cluster_gets_its_own_anchor(self):
        monteregie = [
            city("Longueuil", 45.5369, -73.5105),
            city("Saint-Bruno-de-Montarville", 45.5333, -73.3500),
        ]
        quebec = [
            city("Québec", 46.8139, -71.2080),
            city("Lévis", 46.8033, -71.1782),
        ]
        clusters = compute_anchor_clusters(monteregie + quebec, radius_km=80)
        self.assertEqual(len(clusters), 2)
        member_names_per_cluster = [
            sorted(m["name"] for m in c.members) for c in clusters
        ]
        self.assertIn(sorted(["Lévis", "Québec"]), member_names_per_cluster)
        self.assertIn(
            sorted(["Longueuil", "Saint-Bruno-de-Montarville"]), member_names_per_cluster
        )

    def test_every_city_covered_exactly_once(self):
        cities = [
            city("Longueuil", 45.5369, -73.5105),
            city("Saint-Bruno-de-Montarville", 45.5333, -73.3500),
            city("Québec", 46.8139, -71.2080),
            city("Paris", 48.8566, 2.3522),
        ]
        clusters = compute_anchor_clusters(cities, radius_km=80)
        all_members = [m["name"] for c in clusters for m in c.members]
        self.assertCountEqual(all_members, [c["name"] for c in cities])

    def test_city_without_coordinates_is_its_own_isolated_cluster(self):
        cities = [
            city("Longueuil", 45.5369, -73.5105),
            {"name": "Ville sans coordonnées", "latitude": None, "longitude": None},
        ]
        clusters = compute_anchor_clusters(cities, radius_km=80)
        self.assertEqual(len(clusters), 2)
        isolated = next(c for c in clusters if c.anchor["name"] == "Ville sans coordonnées")
        self.assertEqual(len(isolated.members), 1)

    def test_max_member_distance_km(self):
        cities = [
            city("Longueuil", 45.5369, -73.5105),
            city("Saint-Bruno-de-Montarville", 45.5333, -73.3500),
        ]
        clusters = compute_anchor_clusters(cities, radius_km=80)
        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertGreater(cluster.max_member_distance_km(), 0)
        self.assertLessEqual(cluster.max_member_distance_km(), 80)

    def test_empty_input(self):
        self.assertEqual(compute_anchor_clusters([], radius_km=80), [])


if __name__ == "__main__":
    unittest.main()
