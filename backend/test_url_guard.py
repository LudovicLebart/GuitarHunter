import unittest

from backend.url_guard import is_listing_url, is_storage_image_url


class ListingUrlTest(unittest.TestCase):
    def test_acceptees(self):
        for u in ("https://www.facebook.com/marketplace/item/123/", "https://facebook.com/marketplace/item/1",
                  "https://m.facebook.com/marketplace/item/1", "https://www.kijiji.ca/v-guitare/montreal/x/123"):
            self.assertTrue(is_listing_url(u), u)

    def test_refusees(self):
        for u in ("http://www.facebook.com/marketplace/item/1", "https://127.0.0.1:8000/marketplace/item/1",
                  "http://localhost/v-x/1", "https://100.94.33.54:11434/api", "https://kijiji.ca.evil.com/v-x/1",
                  "https://evil.com/?u=kijiji.ca", "https://evilfacebook.com/x", "file:///etc/passwd",
                  "", None, 123, "https://www.facebook.com/" + "a" * 2100):
            self.assertFalse(is_listing_url(u), u)


class StorageUrlTest(unittest.TestCase):
    def test_bucket_exige_quand_connu(self):
        good = "https://firebasestorage.googleapis.com/v0/b/mon-bucket.app/o/x.jpg?alt=media"
        self.assertTrue(is_storage_image_url(good, bucket="mon-bucket.app"))
        self.assertFalse(is_storage_image_url(good, bucket="autre.app"))
        self.assertTrue(is_storage_image_url("https://storage.googleapis.com/mon-bucket.app/x.jpg", bucket="mon-bucket.app"))

    def test_hotes_refuses(self):
        for u in ("http://storage.googleapis.com/b/x.jpg", "https://evil.com/storage.googleapis.com/b/x.jpg",
                  "https://127.0.0.1/x.jpg", "https://storage.googleapis.com.evil.com/b/x.jpg"):
            self.assertFalse(is_storage_image_url(u, bucket=""), u)


if __name__ == "__main__":
    unittest.main()
