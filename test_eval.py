from evaluator import evaluate

code = """
#include <cstdint>
#include <iomanip>
#include <iostream>
#include <set>
#include <string>
#include <unordered_map>

typedef uint64_t obj_id_t;

/**
 * Implements the Greedy-Dual-Size-Frequency (GDSF) eviction policy.
 *
 * This class manages the cache eviction state. It tracks objects,
 * their sizes, and their frequencies to calculate a priority for
 * eviction. It evicts the object with the *lowest* priority.
 *
 * Priority (H-value) is calculated as: L + (Frequency / Size)
 * where 'L' is the priority of the last evicted item.
 */
class CacheManager {
private:
  /**
   * Node stored in the priority queue (std::set).
   *
   * We use std::set as a min-priority queue. It stores nodes
   * ordered by priority, then by a timestamp as a tie-breaker.
   */
  struct PQNode {
    double priority;
    uint64_t timestamp; // Tie-breaker, incremented on each access
    obj_id_t id;

    // Constructor
    PQNode(double p, uint64_t ts, obj_id_t i)
        : priority(p), timestamp(ts), id(i) {}

    // Comparison operator for std::set
    // Orders by priority (lowest first), then timestamp
    bool operator<(const PQNode &other) const {
      if (priority != other.priority) {
        return priority < other.priority;
      }
      return timestamp < other.timestamp;
    }
  };

  /**
   * Metadata for each object stored in the cache.
   *
   * Stored as the value in the main `cache_objects` map.
   */
  struct CacheObject {
    uint64_t size;
    uint64_t frequency;
    // An iterator pointing to this object's entry in the
    // priority_queue set. This allows for O(log N) removal
    // during a `find` operation.
    std::set<PQNode>::iterator pq_iterator;
  };

  /**
   * Main lookup map.
   *
   * Maps an object's ID to its metadata (size, freq, and
   * iterator into the priority queue).
   */
  std::unordered_map<obj_id_t, CacheObject> cache_objects;

  /**
   * The priority queue.
   *
   * Implemented as an std::set to keep items sorted by priority
   * and allow for efficient removal from anywhere in the queue.
   * The item at `priority_queue.begin()` is the eviction victim.
   */
  std::set<PQNode> priority_queue;

  /**
   *  The 'L' value in GDSF.
   *
   * This is the priority of the last item that was evicted.
   * It's used as the base priority for all new and re-prioritized items.
   */
  double pri_last_evict = 0.0;

  /**
   * A simple counter to use as a timestamp for tie-breaking.
   *
   * This ensures FIFO-like behavior for items with the same priority.
   */
  uint64_t request_counter = 0;

  /**
   * Helper function to calculate an object's priority (H-value).
   *
   * From the original code: pri = L + (freq * 1.0e6 / size)
   * The 1.0e6 is a scaling factor to keep the (freq/size)
   * component significant.
   */
  double calculate_priority(uint64_t freq, uint64_t size) {
    if (size == 0) {
      return pri_last_evict + (double)(freq) * 1.0e6;
    }
    return pri_last_evict + (double)(freq) * 1.0e6 / size;
  }

public:
  /**
   * Default constructor.
   */
  CacheManager() = default;

  /**
   * Finds an object in the cache.
   *
   * If the object is found, its frequency is incremented, its
   * priority is recalculated, and its position in the
   * priority queue is updated.
   *
   * @param obj_id The ID of the object to find.
   * @return true if the object was found (a hit), false otherwise (a miss).
   */
  bool find(obj_id_t obj_id) {
    auto map_iter = cache_objects.find(obj_id);

    if (map_iter == cache_objects.end()) {
      return false;
    }

    CacheObject &obj = map_iter->second;
    priority_queue.erase(obj.pq_iterator);
    obj.frequency += 1;
    double new_pri = calculate_priority(obj.frequency, obj.size);

    PQNode new_node(new_pri, ++request_counter, obj_id);
    auto [set_iter, inserted] = priority_queue.insert(new_node);

    obj.pq_iterator = set_iter;

    return true;
  }

  /**
   * Inserts a new object into the cache.
   *
   * Assumes this is called after a `find` reported a miss.
   * If the object already exists, this function will behave
   * like `find()` and update its priority.
   *
   * @param obj_id The ID of the object to insert.
   * @param obj_size The size of the object (required for GDSF).
   */
  void insert(obj_id_t obj_id, uint64_t obj_size) {
    if (cache_objects.count(obj_id)) {
      find(obj_id);
      return;
    }

    CacheObject new_obj;
    new_obj.size = obj_size;
    new_obj.frequency = 1;

    double pri = calculate_priority(new_obj.frequency, new_obj.size);
    PQNode new_node(pri, ++request_counter, obj_id);
    auto [set_iter, inserted] = priority_queue.insert(new_node);

    new_obj.pq_iterator = set_iter;
    cache_objects[obj_id] = new_obj;
  }

  /**
   * Selects, removes, and returns the victim object to evict.
   *
   * The victim is the object with the *lowest* priority, which
   * will be at the beginning of the `std::set`.
   *
   * @return The obj_id_t of the evicted object. Returns 0 if
   * the cache is empty.
   */
  obj_id_t evict() {
    if (priority_queue.empty()) {
      return 0;
    }

    auto victim_node_it = priority_queue.begin();
    obj_id_t victim_id = victim_node_it->id;
    double victim_priority = victim_node_it->priority;

    cache_objects.erase(victim_id);
    priority_queue.erase(victim_node_it);
    pri_last_evict = victim_priority;

    return victim_id;
  }
};
"""

evaluate(code)
