import os
import random
import string
import argparse
import struct
from pathlib import Path
import time

NODE_SIZE = 1024
MAX_VALUES = 8
MAX_CHILDREN = 64

class PersistentTrie:
    def __init__(self, filename="trie.index"):
        self.filename = filename
        self.file = open(filename, "r+b") if os.path.exists(filename) else open(filename, "w+b")
        if os.path.getsize(filename) == 0:
            self._write_node(0, b'\0', False, [], [])  # root node

    def _read_node(self, node_id):
        self.file.seek(node_id * NODE_SIZE)
        data = self.file.read(NODE_SIZE)
        if not data:
            return None

        char = data[0:1]
        is_terminal = bool(data[1])
        num_values = data[2]
        values = list(struct.unpack("<" + "I" * num_values, data[3:3 + 4 * num_values]))

        num_children = data[35]
        children = []
        for i in range(num_children):
            offset = 36 + i * 3
            child_char = data[offset]
            child_node = struct.unpack("<H", data[offset + 1:offset + 3])[0]
            children.append((child_char, child_node))

        return {
            "char": char,
            "is_terminal": is_terminal,
            "values": values,
            "children": children
        }

    def _write_node(self, node_id, char, is_terminal, values, children):
        buf = bytearray(NODE_SIZE)
        buf[0:1] = char
        buf[1] = 1 if is_terminal else 0
        buf[2] = len(values)
        struct.pack_into("<" + "I" * len(values), buf, 3, *values)
        buf[35] = len(children)
        for i, (c, node_idx) in enumerate(children):
            offset = 36 + i * 3
            buf[offset] = c
            struct.pack_into("<H", buf, offset + 1, node_idx)

        self.file.seek(node_id * NODE_SIZE)
        self.file.write(buf)
        self.file.flush()

    def _find_or_create_child(self, parent_id, target_char):
        node = self._read_node(parent_id)
        for c, node_idx in node["children"]:
            if c == target_char:
                return node_idx

        # Not found, create new
        new_node_id = self._get_next_node_id()
        node["children"].append((target_char, new_node_id))
        self._write_node(parent_id, node["char"], node["is_terminal"], node["values"], node["children"])
        self._write_node(new_node_id, bytes([target_char]), False, [], [])
        return new_node_id

    def _get_next_node_id(self):
        self.file.seek(0, os.SEEK_END)
        size = self.file.tell()
        return size // NODE_SIZE

    def insert(self, word, value):
        word = word.encode("utf-8")
        node_id = 0
        for char in word:
            node_id = self._find_or_create_child(node_id, char)

        # Mark final node as terminal and update value list
        node = self._read_node(node_id)
        if value not in node["values"]:
            if len(node["values"]) < MAX_VALUES:
                node["values"].append(value)
        node["is_terminal"] = True
        self._write_node(node_id, node["char"], node["is_terminal"], node["values"], node["children"])

    def lookup(self, word):
        word = word.encode("utf-8")
        node_id = 0
        for char in word:
            node = self._read_node(node_id)
            for c, child_id in node["children"]:
                if c == char:
                    node_id = child_id
                    break
            else:
                return []  # char not found
        node = self._read_node(node_id)
        return node["values"] if node["is_terminal"] else []

    def close(self):
        self.file.close()


def generate_test_data(filename, total_size_gb=10, avg_line_size=20):
    target_bytes = total_size_gb * 1024**3
    lines_to_generate = target_bytes // avg_line_size

    with open(filename, 'w') as f:
        for _ in range(lines_to_generate):
            word_len = random.randint(3, 10)
            word = ''.join(random.choices(string.ascii_lowercase, k=word_len))
            value = random.randint(1, 65536)
            f.write(f"{word},{value}\n")


def bulk_insert(trie, filename):
    with open(filename, 'r') as f:
        for line in f:
            try:
                word, value = line.strip().split(',')
                trie.insert(word, int(value))
            except Exception as e:
                print(f"Failed to insert line: {line.strip()}, error: {e}")


def prefix_search(trie, prefix):
    prefix_bytes = prefix.encode('utf-8')
    node_id = 0

    # Traverse down to the node matching prefix
    for char in prefix_bytes:
        node = trie._read_node(node_id)
        for c, child_id in node["children"]:
            if c == char:
                node_id = child_id
                break
        else:
            return []  # Prefix not found

    # Perform DFS from here to collect all completions
    results = []

    def dfs(current_id, path):
        node = trie._read_node(current_id)
        if node["is_terminal"]:
            results.append(("".join(path), node["values"]))
        for c, child_id in node["children"]:
            dfs(child_id, path + [chr(c)])

    dfs(node_id, list(prefix))
    return results


def main():
    parser = argparse.ArgumentParser(description="Persistent Trie Operations")
    parser.add_argument("operation", choices=["generate", "insert", "search"], help="Operation to perform")
    parser.add_argument("-f", "--file", type=str, help="File containing data for insertion or prefix search", required=False)
    parser.add_argument("-p", "--prefix", type=str, help="Prefix to search for (only used in search operation)")
    parser.add_argument("-g", "--generate", type=int, default=10, help="Size of data to generate in GB (default: 10GB)")
    
    args = parser.parse_args()

    if args.operation == "generate":
        print(f"Generating {args.generate}GB of test data in {args.file}...")
        generate_test_data(args.file, total_size_gb=args.generate)
        print("Test data generation completed.")

    elif args.operation == "insert":
        print(f"Inserting data from {args.file} into the trie...")
        trie = PersistentTrie("trie.index")
        start_time = time.time()
        bulk_insert(trie, args.file)
        end_time = time.time()
        print(f"Data inserted in {end_time - start_time:.2f} seconds.")
        trie.close()

    elif args.operation == "search":
        if not args.prefix:
            print("Prefix is required for search operation.")
            return
        
        print(f"Searching for prefix '{args.prefix}' in {args.file}...")
        trie = PersistentTrie("trie.index")
        start_time = time.time()
        results = prefix_search(trie, args.prefix)
        end_time = time.time()
        print(f"Search completed in {end_time - start_time:.2f} seconds.")
        
        if results:
            for word, values in results:
                print(f"{word}: {values}")
        else:
            print("No results found.")
        trie.close()


if __name__ == "__main__":
    main()
