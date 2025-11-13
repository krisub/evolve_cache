#include "gdsf.hpp"
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <set>
#include <string>
#include <unordered_map>

// g++ - std = c++ 17 gdsf_tester.cpp - o gdsf_tester

#define CHECK(condition, message)                                              \
  do {                                                                         \
    if (!(condition)) {                                                        \
      std::cerr << "TEST FAILED: " << message << "\n"                          \
                << "    In function: " << __func__ << "\n"                     \
                << "    On line: " << __LINE__ << std::endl;                   \
      exit(1);                                                                 \
    } else {                                                                   \
      std::cout << "  [PASS] " << message << std::endl;                        \
    }                                                                          \
  } while (false)

            typedef uint64_t obj_id_t;

void test_simple_insert_find() {
  std::cout << "\nRunning test_simple_insert_find...\n";
  CacheManager cache;
  cache.insert(1, 100);
  CHECK(cache.find(1) == true, "Should find item 1 after insertion");
  CHECK(cache.find(2) == false, "Should not find item 2");
  CHECK(cache.get_item_count() == 1, "Item count should be 1");
}

void test_simple_eviction() {
  std::cout << "\nRunning test_simple_eviction...\n";
  CacheManager cache;
  cache.insert(1, 100);
  CHECK(cache.get_item_count() == 1, "Item count should be 1 before evict");

  obj_id_t evicted_id = cache.evict();
  CHECK(evicted_id == 1, "Evicted ID should be 1");
  CHECK(cache.get_item_count() == 0, "Item count should be 0 after evict");
  CHECK(cache.find(1) == false, "Should not find item 1 after eviction");
}

void test_evict_empty() {
  std::cout << "\nRunning test_evict_empty...\n";
  CacheManager cache;
  obj_id_t evicted_id = cache.evict();
  CHECK(evicted_id == 0, "Evicting from empty cache should return 0");
  CHECK(cache.get_item_count() == 0, "Item count should remain 0");
}

void test_lru_behavior_same_size() {
  std::cout << "\nRunning test_lru_behavior_same_size...\n";
  CacheManager cache;
  cache.insert(1, 100); // timestamp 1
  cache.insert(2, 100); // timestamp 2
  cache.insert(3, 100); // timestamp 3

  cache.find(1); // Item 1 accessed, gets new timestamp (4)

  // Priorities are all L + 1/100.
  // Eviction order should be by timestamp (FIFO): 2, then 3, then 1.
  CHECK(cache.evict() == 2, "Evict 2 (oldest, un-accessed)");
  CHECK(cache.evict() == 3, "Evict 3 (next oldest, un-accessed)");
  CHECK(cache.evict() == 1, "Evict 1 (last, accessed)");
  CHECK(cache.get_item_count() == 0, "Cache should be empty");
}

void test_frequency_behavior_same_size() {
  std::cout << "\nRunning test_frequency_behavior_same_size...\n";
  CacheManager cache;
  cache.insert(1, 100);
  cache.insert(2, 100);

  cache.find(1); // Freq(1) = 2
  cache.find(1); // Freq(1) = 3
  cache.find(2); // Freq(2) = 2

  // P(1) = L + 3e6/100
  // P(2) = L + 2e6/100
  // Item 2 has lower priority and should be evicted first.
  CHECK(cache.evict() == 2, "Evict 2 (lower frequency)");
  CHECK(cache.evict() == 1, "Evict 1 (higher frequency)");
}

void test_size_behavior_same_frequency() {
  std::cout << "\nRunning test_size_behavior_same_frequency...\n";
  CacheManager cache;
  cache.insert(1, 1000); // Large object
  cache.insert(2, 10);   // Small object

  // Both have Freq = 1
  // P(1) = L + 1e6 / 1000 = L + 1000
  // P(2) = L + 1e6 / 10   = L + 100000
  // Item 1 (large) has much lower priority.
  CHECK(cache.evict() == 1, "Evict 1 (large object)");
  CHECK(cache.evict() == 2, "Evict 2 (small object)");
}

void test_gdsf_combined() {
  std::cout << "\nRunning test_gdsf_combined...\n";
  CacheManager cache;
  cache.insert(1, 1000); // Large object
  cache.insert(2, 10);   // Small object

  // Access large object 100 times
  for (int i = 0; i < 99; ++i) { // 1 (insert) + 99 (find) = 100
    cache.find(1);
  }
  // Access small object 5 times
  for (int i = 0; i < 4; ++i) { // 1 (insert) + 4 (find) = 5
    cache.find(2);
  }

  // Freq(1) = 100, Size(1) = 1000
  // Freq(2) = 5,   Size(2) = 10
  // P(1) = L + 100e6 / 1000 = L + 100,000
  // P(2) = L + 5e6 / 10     = L + 500,000
  // Item 1 (large) still has lower priority despite high freq.
  CHECK(cache.evict() == 1, "Evict 1 (large, lower priority)");
  CHECK(cache.evict() == 2, "Evict 2 (small, higher priority)");
}

void test_l_value_update() {
  std::cout << "\nRunning test_l_value_update...\n";
  CacheManager cache;
  CHECK(std::abs(cache.get_l_value() - 0.0) < 1e-9,
        "L-value should be 0.0 initially");

  cache.insert(1, 1000); // P(1) = 0 + 1e6/1000 = 1000
  cache.insert(2, 1000); // P(2) = 0 + 1e6/1000 = 1000 (later timestamp)
  CHECK(cache.get_item_count() == 2, "Cache has 2 items");

  // Evict 1. P(1) is 1000.
  obj_id_t evicted_id = cache.evict();
  CHECK(evicted_id == 1, "Evict 1 (lower timestamp)");
  CHECK(std::abs(cache.get_l_value() - 1000.0) < 1e-9,
        "L-value should update to 1000.0");

  // Insert 3. Its priority will use the new L-value.
  // P(3) = 1000 + 1e6/100 = 1000 + 10000 = 11000
  cache.insert(3, 100);

  // P(2) is still 1000.
  // Evict 2.
  evicted_id = cache.evict();
  CHECK(evicted_id == 2, "Evict 2 (priority 1000)");
  CHECK(std::abs(cache.get_l_value() - 1000.0) < 1e-9,
        "L-value should still be 1000.0");

  // Evict 3.
  evicted_id = cache.evict();
  CHECK(evicted_id == 3, "Evict 3 (priority 11000)");
  CHECK(std::abs(cache.get_l_value() - 11000.0) < 1e-9,
        "L-value should update to 11000.0");
}

// --- Main Test Runner ---
int main() {
  std::cout << "Starting GDSF CacheManager Test Suite..." << std::endl;
  std::cout << std::fixed << std::setprecision(2);

  test_simple_insert_find();
  test_simple_eviction();
  test_evict_empty();
  test_lru_behavior_same_size();
  test_frequency_behavior_same_size();
  test_size_behavior_same_frequency();
  test_gdsf_combined();
  test_l_value_update();

  std::cout << "\n---------------------------------" << std::endl;
  std::cout << "All GDSF tests passed successfully!" << std::endl;
  std::cout << "---------------------------------" << std::endl;

  return 0;
}