from __future__ import annotations

from iac_review.core.diff import changed_lines

PATCH = """@@ -1,3 +1,4 @@
 resource "azurerm_storage_account" "a" {
-  account_tier = "Premium"
+  account_tier = "Standard"
+  min_tls_version = "TLS1_2"
 }
@@ -20,2 +21,2 @@
-old
+new
"""


def test_changed_lines_are_post_change_positions() -> None:
    assert changed_lines(PATCH) == {2, 3, 21}


def test_unknown_patch_means_no_constraint() -> None:
    assert changed_lines("") == frozenset()
