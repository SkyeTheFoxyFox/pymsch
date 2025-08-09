from __future__ import annotations

import base64
import struct
import zlib
import csv
from pathlib import Path
from enum import Enum
from typing import Iterable, Literal, overload

import pyperclip

class Block:
    def __init__(self, block: Content, x: int, y: int, config: _ByteObject, rotation: int):
        if not isinstance(block.value, ContentBlock):
            raise ValueError(
                f"Invalid block type (expected {ContentTypes.BLOCK} but got {block.value.type}): {block}"
            )
        self.block = block
        self.x = x 
        self.y = y 
        self.config = config 
        self.rotation = rotation

    @property
    def value(self) -> ContentBlock:
        """Equivalent to `self.block.value`, but correctly typed."""
        assert isinstance(self.block.value, ContentBlock)
        return self.block.value

    def get_block_name(self):
        return(self.block.name.lower().replace("_", "-"))

    def set_config(self, config: _ByteObject):
        self.config = config

    def __repr__(self):
        return(f"{self.get_block_name()}({self.x}, {self.y})")

class Schematic:

    def __init__(self):
        self.tiles = list[Block]()
        self.tags = {"name": "unnamed"}
        self.labels = list[str]()
        self._filled_list = list[tuple[int, int]]()

    def __repr__(self):
        return f"Schematic '{self.tags['name']}' with {len(self.tiles)} blocks"

    def copy(self):
        a = Schematic()
        a.tiles = self.tiles.copy()
        a.tags = self.tags.copy()
        a.labels = self.labels.copy()
        a._filled_list = self._filled_list.copy()
        return(a)

    def add_block(self, tile: Block, do_collision: bool = True):
        if not (self._test_block_collision(tile) and do_collision):
            self.tiles.append(tile)
            self._add_block_collision(tile)
            return(tile)
        else:
            return(None)

    def add_schem(self, schem: Schematic, x: int, y: int):

        _, _, offset_x, offset_y = schem.get_dimensions(offsets = True)

        for tile in schem.tiles:
            self.add_block(Block(tile.block, tile.x + x + offset_x, tile.y + y + offset_y, tile.config, tile.rotation))

    @classmethod
    def _read(cls, data: bytes | bytearray):
        self = Schematic()
        if data[:4] != b"msch":
            raise Exception("Invalid msch data")
        data = data[5:]
        data = bytearray(zlib.decompress(data))
        
        _ByteUtils.pop_int(data, 2) # width
        _ByteUtils.pop_int(data, 2) # height

        tag_count = _ByteUtils.pop_int(data, 1)
        for _ in range(tag_count):
            tag = _ByteUtils.pop_UTF(data)
            value = _ByteUtils.pop_UTF(data)
            self.tags[tag] = value

        if "labels" in self.tags:
            labels = self.tags.pop("labels")
            self.labels = labels[1:-1].split(",")
            

        types = list[str]()
        type_count = _ByteUtils.pop_int(data, 1)
        for _ in range(type_count):
            types.append(_ByteUtils.pop_UTF(data))

        block_count = _ByteUtils.pop_int(data, 4)
        for _ in range(block_count):
            block_index = _ByteUtils.pop_int(data, 1)
            block_x = _ByteUtils.pop_int(data, 2)
            block_y = _ByteUtils.pop_int(data, 2)
            block_config = _ByteUtils.pop_object(data)
            block_rotation = _ByteUtils.pop_int(data, 1)
            block_type = Content[types[block_index].upper().replace('-', '_')]
            self.add_block(Block(block_type, block_x, block_y, block_config, block_rotation))    

        return(self)

    @classmethod
    def read_str(cls, string: str):
        return Schematic._read(base64.standard_b64decode(bytearray(string, "utf8")))

    @classmethod
    def read_file(cls, file_path: str):
        with open(file_path, "rb") as file:
            data = bytearray(file.read())
            return Schematic._read(data)

    def _write(self):

        schem = self.copy()

        types_list = list[str]()
        for tile in schem.tiles:
            if(tile.get_block_name() not in types_list):
                types_list.append(tile.get_block_name())
        
        width, height, offset_x, offset_y = schem.get_dimensions(offsets = True)

        for block in schem.tiles:
            block.x = block.x + offset_x
            block.y = block.y + offset_y

        buffer = _ByteBuffer()

        buffer.writeUShort(width)
        buffer.writeUShort(height)

        labels = "["
        for label in schem.labels:
            labels += f"{label},"
        labels = labels.rstrip(',') + ']'

        schem.set_tag('labels', labels)

        buffer.writeByte(len(schem.tags))
        for k, v in schem.tags.items():
            buffer.writeUTF(k)
            buffer.writeUTF(v)
        buffer.writeByte(len(types_list)) #dictionary
        for t in types_list:
            buffer.writeUTF(t)
        
        buffer.writeInt(len(schem.tiles))
        for t in schem.tiles:
            buffer.writeByte(types_list.index(t.get_block_name())) #dictionary index
            buffer.writeUShort(t.x) #x
            buffer.writeUShort(t.y) #y
            buffer.writeObject(t.config) #config
            buffer.writeByte(t.rotation) #rotation

        #print(b"msch\x01"+zlib.compress(buffer.data))
        return(b"msch\x01"+zlib.compress(buffer.data))

    def write_str(self):
        return base64.standard_b64encode(self._write()).decode()

    def write_clipboard(self):
        pyperclip.copy(self.write_str())

    def write_file(self, file_path: str):
        file = open(file_path, 'wb')
        file.write(self._write())
        file.close()

    def set_tag(self, tag: str, value: str):
        self.tags[tag] = value

    def add_label(self, label: str):
        self.labels.append(label)

    def _add_block_collision(self, block: Block):
        smallest_x = block.x - ((block.value.size - 1) // 2)
        smallest_y = block.y - ((block.value.size - 1) // 2)

        for x in range(smallest_x, smallest_x + block.value.size, 1):
            for y in range(smallest_y, smallest_y + block.value.size, 1):
                if((x, y) not in self._filled_list):
                    self._filled_list.append((x, y))

    def _test_block_collision(self, block: Block):
        smallest_x = block.x - ((block.value.size - 1) // 2)
        smallest_y = block.y - ((block.value.size - 1) // 2)

        for x in range(smallest_x, smallest_x + block.value.size, 1):
            for y in range(smallest_y, smallest_y + block.value.size, 1):
                if((x, y) in self._filled_list):
                    return(True)
        return(False)

    def get_block(self, x: int, y: int):
        for block in self.tiles:
            smallest_x = block.x - ((block.value.size - 1) // 2)
            smallest_y = block.y - ((block.value.size - 1) // 2)
            if(x >= smallest_x and x < smallest_x + block.value.size and y >= smallest_y and y < smallest_y + block.value.size):
                return(block)
        return(None)

    @overload
    def get_dimensions(self, offsets: Literal[True]) -> tuple[int, int, int, int]:
        """Returns: width, height, offset_x, offset_y"""

    @overload
    def get_dimensions(self, offsets: Literal[False] = False) -> tuple[int, int]:
        """Returns: width, height"""

    def get_dimensions(self, offsets: bool = False):

        if(len(self.tiles) == 0):
            if not offsets:
                return(0, 0)
            else:
                return(0, 0, 0, 0)

        b = self.tiles[0]

        width = b.x - ((b.value.size - 1) // 2)
        height = b.y - ((b.value.size - 1) // 2)
        offset_x = b.x + (b.value.size // 2) + 1
        offset_y = b.y + (b.value.size // 2) + 1

        for block in self.tiles:
            offset_x = min(offset_x, block.x - ((block.value.size - 1) // 2))
            offset_y = min(offset_y, block.y - ((block.value.size - 1) // 2))
            width = max(width, block.x + (block.value.size // 2) + 1)
            height = max(height, block.y + (block.value.size // 2) + 1)
        offset_x *= -1
        offset_y *= -1
        width += offset_x
        height += offset_y
        if not offsets:
            return(width, height)
        else:
            return(width, height, offset_x, offset_y)

class ContentTypes(Enum):
    ITEM = 0
    BLOCK = 1
    MECH_UNUSED = 2
    BULLET = 3
    LIQUID = 4
    STATUS = 5
    UNIT = 6
    WEATHER = 7
    EFFECT_UNUSED = 8
    SECTOR = 9
    LOADOUT_UNUSED = 10
    TYPEID_UNUSED = 11
    ERROR = 12
    PLANET = 13
    AMMO_UNUSED = 14
    TEAM = 15
    UNIT_COMMAND = 16
    UNIT_STANCE = 17

class ContentType:
    def __init__(self, type: ContentTypes, id: int):
        self.type = type
        self.id = id

class ContentBlock(ContentType):
    def __init__(self, id: int, size: int, building: bool):
        self.type = ContentTypes.BLOCK
        self.id = id
        self.size = size
        self.building = building

def _parse_mimex_file(path: Path) -> list[dict]:
    output = []
    with open(path, "r") as mimexfile:
        reader = csv.reader(mimexfile, delimiter=';')
        rows = list(reader)[1:]
        columns = rows[0]
        data = rows[1:]
    for row in data:
        item = {}
        for index, value in enumerate(row):
            item[columns[index]] = value
        output.append(item)
    return output

def _define_content(mimex_data_path):
    content_dict = {}

    block_data = _parse_mimex_file(mimex_data_path/"mimex-blocks.txt")
    for block in block_data:
        content_dict[block["name"].upper().replace('-', '_')] = ContentBlock(int(block["id"]), int(block["size"]), block["logicId"] != '-1')

    unit_data = _parse_mimex_file(mimex_data_path/"mimex-units.txt")
    for unit in unit_data:
        content_dict[unit["name"].upper().replace('-', '_')] = ContentType(ContentTypes.UNIT, int(unit["id"]))

    item_data = _parse_mimex_file(mimex_data_path/"mimex-items.txt")
    for item in item_data:
        content_dict[item["name"].upper().replace('-', '_')] = ContentType(ContentTypes.ITEM, int(item["id"]))

    liquid_data = _parse_mimex_file(mimex_data_path/"mimex-liquids.txt")
    for liquid in liquid_data:
        content_dict[liquid["name"].upper().replace('-', '_')] = ContentType(ContentTypes.LIQUID, int(liquid["id"]))

    return content_dict

Content = Enum("Content", _define_content(Path(__file__).parent/"mimex-data/data/be"))

class ContentLists:
    BLOCKS = list[Content]()
    BUILDINGS = list[Content]()
    ITEMS = list[Content]()
    UNITS = list[Content]()
    LIQUIDS = list[Content]()

    REVERSE_LOOKUP = dict[int, dict[int, Content]]()

    for t in ContentTypes:
        REVERSE_LOOKUP[t.value] = {}

    for content in Content:
        REVERSE_LOOKUP[content.value.type.value][content.value.id] = content
        
        if(content.value.type == ContentTypes.BLOCK):
            BLOCKS.append(content)
            if content.value.building:
                BUILDINGS.append(content)
        elif(content.value.type == ContentTypes.ITEM):
            ITEMS.append(content)
        elif(content.value.type == ContentTypes.UNIT):
            UNITS.append(content)
        elif(content.value.type == ContentTypes.LIQUID):
            LIQUIDS.append(content)

class double(float):
    pass

class long(int):
    pass

class Point:
    def __init__(self, x: int, y: int):
        self.x = x
        self.y = y

class PointArray:
    def __init__(self, array: Iterable[Point] = []):
        self.array = list[Point]()
        a = 0
        for i in array:
            self.insert(a, i)
            a += 1

    def __getitem__(self, index: int):
        return(self.array[index])

    def __setitem__(self, index: int, value: Point):
        self.array[index] = value

    def insert(self, index: int, value: Point):
        self.array.insert(index, value)

    def __iter__(self):
        return(iter(self.array))

    def __len__(self):
        return(len(self.array))

    def append(self, item: Point):
        self.array.append(item)

class ProcessorConfig:
    def __init__(self, code: str, links: list[ProcessorLink]):
        self.code = code
        self.links = links

    def compress(self):
        buffer = _ByteBuffer()

        buffer.writeByte(1)

        buffer.writeBytesFromStr(self.code)

        buffer.writeInt(len(self.links))
        for link in self.links:
            buffer.writeUTF(link.name)
            buffer.writeShort(link.x)
            buffer.writeShort(link.y)

        return(bytearray(zlib.compress(buffer.data)))

    @classmethod
    def decompress(cls, data: bytes | bytearray):
        self = ProcessorConfig("", [])
        data = bytearray(zlib.decompress(data))
        _ByteUtils.pop_bytes(data, 1)
        code_len = _ByteUtils.pop_int(data, 4)
        self.code = str(_ByteUtils.pop_bytes(data, code_len), "ascii")

        link_len = _ByteUtils.pop_int(data, 4)
        for _ in range(link_len):
            link_name = _ByteUtils.pop_UTF(data)
            link_x = _ByteUtils.pop_int(data, 2, signed=True)
            link_y = _ByteUtils.pop_int(data, 2, signed=True)
            self.links.append(ProcessorLink(link_x, link_y, link_name))
        return self

    def __repr__(self):
        print_code = ""
        for c in self.code:
            if(c == "\n"):
                print_code += "; "
            else:
                print_code += c
        return(f"ProcessorConfig(code = \"{print_code}\", links = {self.links})")

class ProcessorLink:
    def __init__(self, x: int, y: int, name: str):
        self.x = x
        self.y = y
        self.name = name

    def __repr__(self):
        return(f"ProcessorLink(pos = ({self.x}, {self.y}), name = \"{self.name}\")")

_ByteObject = (
    int
    | long
    | float
    | str
    | Content
    | Point
    | PointArray
    | bool
    | double
    | bytearray
    | ProcessorConfig
    | list["_ByteObject"]
    | None
)

class _ByteBuffer():
    def __init__(self):
        self.data = bytearray()
        
    def writeUShort(self, var: int):
        self.data += struct.pack(">H", var)

    def writeShort(self, var: int):
        self.data += struct.pack(">h", var)

    def writeUTF(self, var: str):
        self.writeUShort(len(var.encode("UTF")))
        self.data += bytes(var.encode("UTF"))

    def writeString(self, var: str):
        self.writeByte(1)
        self.writeUTF(var)

    def writeBytesFromStr(self, var: str):
        self.writeInt(len(var))
        self.data.extend(map(ord, var))
        
    def writeByte(self, var: int):
        self.data += struct.pack("b", var)

    def writeUByte(self, var: int):
        self.data += struct.pack("B", var)
        
    def writeInt(self, var: int):
        self.data += struct.pack(">i", var)

    def writeLong(self, var: long):
        self.data += struct.pack(">l", var)

    def writeFloat(self, var: float):
        self.data += struct.pack(">f", var)

    def writeDouble(self, var: double):
        self.data += struct.pack(">d", var)

    def writeBool(self, var: bool):
        self.data += struct.pack("?", var)

    def writeObject(self, obj: _ByteObject):
        if(obj is None):
            self.writeByte(0)
        elif(type(obj) is int):
            self.writeByte(1)
            self.writeInt(obj)
        elif(type(obj) is long):
            self.writeByte(2)
            self.writeLong(obj)
        elif(type(obj) is float):
            self.writeByte(3)
            self.writeFloat(obj)
        elif(type(obj) is str):
            self.writeByte(4)
            self.writeString(obj)
        elif(type(obj) is Content):
            self.writeByte(5)
            self.writeByte(obj.value.type.value)
            self.writeUShort(obj.value.id)
        #elif(type(obj) is str): #intSeq
        #    self.writeByte(6)
        elif(type(obj) is Point):
            self.writeByte(7)
            self.writeInt(obj.x)
            self.writeInt(obj.y)
        elif(type(obj) is PointArray): #point list
            self.writeByte(8)
            self.writeByte(len(obj))
            for point in obj:
                self.writeShort(point.x)
                self.writeShort(point.y)
        #elif(type(obj) is str): #tech node
        #    self.writeByte(9)
        elif(type(obj) is bool):
            self.writeByte(10)
            self.writeBool(obj)
        elif(type(obj) is double):
            self.writeByte(11)
            self.writeDouble(obj)
        #elif(type(obj) is str): #Building
        #    self.writeByte(12)
        #elif(type(obj) is str): #BuildingBox
        #    self.writeByte(12)
        #elif(type(obj) is str): #LAccess
        #    self.writeByte(13)
        elif(type(obj) is bytearray): #Byte array
            self.writeByte(14)
            self.writeInt(len(obj))
            for b in obj:
                self.writeUByte(b)
        elif(type(obj) is ProcessorConfig): #Byte array
            self.writeByte(14)
            data = obj.compress()
            self.writeInt(len(data))
            for b in data:
                self.writeUByte(b)
        #elif(type(obj) is str): #Bool array
        #    self.writeByte(16)
        #elif(type(obj) is str): #Unit
        #    self.writeByte(17)
        #elif(type(obj) is str): #Vec2 array
        #    self.writeByte(18)
        #elif(type(obj) is str): #Vec2
        #    self.writeByte(19)
        #elif(type(obj) is str): #Team
        #    self.writeByte(20)
        #elif(type(obj) is str): #int array
        #    self.writeByte(21)
        elif(type(obj) is list): #Object array / list
            self.writeByte(22)
            self.writeInt(len(obj))
            for i in obj:
                self.writeObject(i)
        #elif(type(obj) is dict): #Object array / list
        #    self.writeByte(22)
        #    self.writeInt(len(obj))
        #    for k, v in obj.items():
        #        self.writeObject(v)
        #elif(type(obj) is str): #UnitCommand
        #   self.writeByte(23)
        else:
           print("Unknown object type")

class _ByteUtils:
    @staticmethod
    def pop_bytes(data: bytearray, byte_count: int):
        out_bytes = bytearray()
        for _ in range(byte_count):
            out_bytes.append(data.pop(0))
        return(out_bytes)

    @staticmethod
    def pop_int(data: bytearray, byte_count: int, signed: bool = False):
        return int.from_bytes(
            _ByteUtils.pop_bytes(data, byte_count),
            byteorder="big",
            signed=signed,
        )

    @staticmethod
    def pop_float(data: bytearray) -> float:
        return struct.unpack('f', _ByteUtils.pop_bytes(data, 4))[0]

    @staticmethod
    def pop_double(data: bytearray) -> double:
        return double(struct.unpack('d', _ByteUtils.pop_bytes(data, 8))[0])

    @staticmethod
    def pop_bool(data: bytearray) -> bool:
        return struct.unpack('?', _ByteUtils.pop_bytes(data, 1))[0]

    @staticmethod
    def pop_UTF(data: bytearray):
        char_count = _ByteUtils.pop_int(data, 2)
        return str(_ByteUtils.pop_bytes(data, char_count), "UTF")

    @staticmethod
    def pop_object(data: bytearray) -> _ByteObject:
        obj_type = _ByteUtils.pop_int(data, 1)
        match obj_type:
            case 0: #null
                return None
            case 1: #int
                return _ByteUtils.pop_int(data, 4, signed=True)
            case 2: #long
                return _ByteUtils.pop_int(data, 8, signed=True)
            case 3: #float
                return _ByteUtils.pop_float(data)
            case 4: #string
                exists = _ByteUtils.pop_bytes(data, 1)
                if(exists):
                    return _ByteUtils.pop_UTF(data)
                else:
                    return None
            case 5: #content
                type_id = _ByteUtils.pop_int(data, 1)
                content_id = _ByteUtils.pop_int(data, 2)
                return ContentLists.REVERSE_LOOKUP[type_id][content_id]
            case 7: #point
                x = _ByteUtils.pop_int(data, 4, signed=True)
                y = _ByteUtils.pop_int(data, 4, signed=True)
                return Point(x, y)
            case 8:
                out_arr = PointArray()
                arr_len = _ByteUtils.pop_int(data, 1)
                for _ in range(arr_len):
                    x = _ByteUtils.pop_int(data, 2, signed=True)
                    y = _ByteUtils.pop_int(data, 2, signed=True)
                    out_arr.append(Point(x, y))
                return out_arr
            case 10: #bool
                return _ByteUtils.pop_bool(data)
            case 11: #double
                return _ByteUtils.pop_double(data)
            case 14: #byte array
                arr_len = _ByteUtils.pop_int(data, 4)
                return _ByteUtils.pop_bytes(data, arr_len)
            case 22: #object array
                out_list = list[_ByteObject]()
                arr_len = _ByteUtils.pop_int(data, 4)
                for _ in range(arr_len):
                    out_list.append(_ByteUtils.pop_object(data))
                return out_list
            case _:
                raise Exception(f"Unknown object type {obj_type}")