from __future__ import annotations

import base64
import struct
import zlib
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
    def __init__(self, id: int, size: int):
        self.type = ContentTypes.BLOCK
        self.id = id
        self.size = size

class Content(Enum):
    COPPER = ContentType(ContentTypes.ITEM, 0)
    LEAD = ContentType(ContentTypes.ITEM, 1)
    METAGLASS = ContentType(ContentTypes.ITEM, 2)
    GRAPHITE = ContentType(ContentTypes.ITEM, 3)
    SAND = ContentType(ContentTypes.ITEM, 4)
    COAL = ContentType(ContentTypes.ITEM, 5)
    TITANIUM = ContentType(ContentTypes.ITEM, 6)
    THORIUM = ContentType(ContentTypes.ITEM, 7)
    SCRAP = ContentType(ContentTypes.ITEM, 8)
    SILICON = ContentType(ContentTypes.ITEM, 9)
    PLASTANIUM = ContentType(ContentTypes.ITEM, 10)
    PHASE_FABRIC = ContentType(ContentTypes.ITEM, 11)
    SURGE_ALLOY = ContentType(ContentTypes.ITEM, 12)
    SPORE_POD = ContentType(ContentTypes.ITEM, 13)
    BLAST_COMPOUND = ContentType(ContentTypes.ITEM, 14)
    PYRATITE = ContentType(ContentTypes.ITEM, 15)
    BERYLLIUM = ContentType(ContentTypes.ITEM, 16)
    TUNGSTEN = ContentType(ContentTypes.ITEM, 17)
    OXIDE = ContentType(ContentTypes.ITEM, 18)
    CARBIDE = ContentType(ContentTypes.ITEM, 19)
    FISSILE_MATTER = ContentType(ContentTypes.ITEM, 20)
    DORMANT_CYST = ContentType(ContentTypes.ITEM, 21)

    AIR = ContentBlock(0, 1)
    SPAWN = ContentBlock(1, 1)
    CLIFF = ContentBlock(2, 1)
    BUILD1 = ContentBlock(3, 1)
    BUILD2 = ContentBlock(4, 2)
    BUILD3 = ContentBlock(5, 3)
    BUILD4 = ContentBlock(6, 4)
    BUILD5 = ContentBlock(7, 5)
    BUILD6 = ContentBlock(8, 6)
    BUILD7 = ContentBlock(9, 7)
    BUILD8 = ContentBlock(10, 8)
    BUILD9 = ContentBlock(11, 9)
    BUILD10 = ContentBlock(12, 10)
    BUILD11 = ContentBlock(13, 11)
    BUILD12 = ContentBlock(14, 12)
    BUILD13 = ContentBlock(15, 13)
    BUILD14 = ContentBlock(16, 14)
    BUILD15 = ContentBlock(17, 15)
    BUILD16 = ContentBlock(18, 16)
    DEEP_WATER = ContentBlock(19, 1)
    SHALLOW_WATER = ContentBlock(20, 1)
    TAINTED_WATER = ContentBlock(21, 1)
    DEEP_TAINTED_WATER = ContentBlock(22, 1)
    DARKSAND_TAINTED_WATER = ContentBlock(23, 1)
    SAND_WATER = ContentBlock(24, 1)
    DARKSAND_WATER = ContentBlock(25, 1)
    TAR = ContentBlock(26, 1)
    POOLED_CRYOFLUID = ContentBlock(27, 1)
    MOLTEN_SLAG = ContentBlock(28, 1)
    SPACE = ContentBlock(29, 1)
    EMPTY = ContentBlock(30, 1)
    STONE = ContentBlock(31, 1)
    CRATER_STONE = ContentBlock(32, 1)
    CHAR = ContentBlock(33, 1)
    BASALT = ContentBlock(34, 1)
    HOTROCK = ContentBlock(35, 1)
    MAGMAROCK = ContentBlock(36, 1)
    SAND_FLOOR = ContentBlock(37, 1)
    DARKSAND = ContentBlock(38, 1)
    DIRT = ContentBlock(39, 1)
    MUD = ContentBlock(40, 1)
    DACITE = ContentBlock(41, 1)
    RHYOLITE = ContentBlock(42, 1)
    RHYOLITE_CRATER = ContentBlock(43, 1)
    ROUGH_RHYOLITE = ContentBlock(44, 1)
    REGOLITH = ContentBlock(45, 1)
    YELLOW_STONE = ContentBlock(46, 1)
    CARBON_STONE = ContentBlock(47, 1)
    FERRIC_STONE = ContentBlock(48, 1)
    FERRIC_CRATERS = ContentBlock(49, 1)
    BERYLLIC_STONE = ContentBlock(50, 1)
    CRYSTALLINE_STONE = ContentBlock(51, 1)
    CRYSTAL_FLOOR = ContentBlock(52, 1)
    YELLOW_STONE_PLATES = ContentBlock(53, 1)
    RED_STONE = ContentBlock(54, 1)
    DENSE_RED_STONE = ContentBlock(55, 1)
    RED_ICE = ContentBlock(56, 1)
    ARKYCITE_FLOOR = ContentBlock(57, 1)
    ARKYIC_STONE = ContentBlock(58, 1)
    RHYOLITE_VENT = ContentBlock(59, 1)
    CARBON_VENT = ContentBlock(60, 1)
    ARKYIC_VENT = ContentBlock(61, 1)
    YELLOW_STONE_VENT = ContentBlock(62, 1)
    RED_STONE_VENT = ContentBlock(63, 1)
    CRYSTALLINE_VENT = ContentBlock(64, 1)
    REDMAT = ContentBlock(65, 1)
    BLUEMAT = ContentBlock(66, 1)
    GRASS = ContentBlock(67, 1)
    SALT = ContentBlock(68, 1)
    SNOW = ContentBlock(69, 1)
    ICE = ContentBlock(70, 1)
    ICE_SNOW = ContentBlock(71, 1)
    SHALE = ContentBlock(72, 1)
    MOSS = ContentBlock(73, 1)
    CORE_ZONE = ContentBlock(74, 1)
    SPORE_MOSS = ContentBlock(75, 1)
    STONE_WALL = ContentBlock(76, 1)
    SPORE_WALL = ContentBlock(77, 1)
    DIRT_WALL = ContentBlock(78, 1)
    DACITE_WALL = ContentBlock(79, 1)
    ICE_WALL = ContentBlock(80, 1)
    SNOW_WALL = ContentBlock(81, 1)
    DUNE_WALL = ContentBlock(82, 1)
    REGOLITH_WALL = ContentBlock(83, 1)
    YELLOW_STONE_WALL = ContentBlock(84, 1)
    RHYOLITE_WALL = ContentBlock(85, 1)
    CARBON_WALL = ContentBlock(86, 1)
    FERRIC_STONE_WALL = ContentBlock(87, 1)
    BERYLLIC_STONE_WALL = ContentBlock(88, 1)
    ARKYIC_WALL = ContentBlock(89, 1)
    CRYSTALLINE_STONE_WALL = ContentBlock(90, 1)
    RED_ICE_WALL = ContentBlock(91, 1)
    RED_STONE_WALL = ContentBlock(92, 1)
    RED_DIAMOND_WALL = ContentBlock(93, 1)
    SAND_WALL = ContentBlock(94, 1)
    SALT_WALL = ContentBlock(95, 1)
    SHRUBS = ContentBlock(96, 1)
    SHALE_WALL = ContentBlock(97, 1)
    SPORE_PINE = ContentBlock(98, 1)
    SNOW_PINE = ContentBlock(99, 1)
    PINE = ContentBlock(100, 1)
    WHITE_TREE_DEAD = ContentBlock(101, 1)
    WHITE_TREE = ContentBlock(102, 1)
    SPORE_CLUSTER = ContentBlock(103, 1)
    REDWEED = ContentBlock(104, 1)
    PUR_BUSH = ContentBlock(105, 1)
    YELLOWCORAL = ContentBlock(106, 1)
    BOULDER = ContentBlock(107, 1)
    SNOW_BOULDER = ContentBlock(108, 1)
    SHALE_BOULDER = ContentBlock(109, 1)
    SAND_BOULDER = ContentBlock(110, 1)
    DACITE_BOULDER = ContentBlock(111, 1)
    BASALT_BOULDER = ContentBlock(112, 1)
    CARBON_BOULDER = ContentBlock(113, 1)
    FERRIC_BOULDER = ContentBlock(114, 1)
    BERYLLIC_BOULDER = ContentBlock(115, 1)
    YELLOW_STONE_BOULDER = ContentBlock(116, 1)
    ARKYIC_BOULDER = ContentBlock(117, 1)
    CRYSTAL_CLUSTER = ContentBlock(118, 1)
    VIBRANT_CRYSTAL_CLUSTER = ContentBlock(119, 1)
    CRYSTAL_BLOCKS = ContentBlock(120, 1)
    CRYSTAL_ORBS = ContentBlock(121, 1)
    CRYSTALLINE_BOULDER = ContentBlock(122, 1)
    RED_ICE_BOULDER = ContentBlock(123, 1)
    RHYOLITE_BOULDER = ContentBlock(124, 1)
    RED_STONE_BOULDER = ContentBlock(125, 1)
    METAL_FLOOR = ContentBlock(126, 1)
    METAL_FLOOR_DAMAGED = ContentBlock(127, 1)
    METAL_FLOOR_2 = ContentBlock(128, 1)
    METAL_FLOOR_3 = ContentBlock(129, 1)
    METAL_FLOOR_4 = ContentBlock(130, 1)
    METAL_FLOOR_5 = ContentBlock(131, 1)
    DARK_PANEL_1 = ContentBlock(132, 1)
    DARK_PANEL_2 = ContentBlock(133, 1)
    DARK_PANEL_3 = ContentBlock(134, 1)
    DARK_PANEL_4 = ContentBlock(135, 1)
    DARK_PANEL_5 = ContentBlock(136, 1)
    DARK_PANEL_6 = ContentBlock(137, 1)
    DARK_METAL = ContentBlock(138, 1)
    PEBBLES = ContentBlock(139, 1)
    TENDRILS = ContentBlock(140, 1)
    ORE_COPPER = ContentBlock(141, 1)
    ORE_LEAD = ContentBlock(142, 1)
    ORE_SCRAP = ContentBlock(143, 1)
    ORE_COAL = ContentBlock(144, 1)
    ORE_TITANIUM = ContentBlock(145, 1)
    ORE_THORIUM = ContentBlock(146, 1)
    ORE_BERYLLIUM = ContentBlock(147, 1)
    ORE_TUNGSTEN = ContentBlock(148, 1)
    ORE_CRYSTAL_THORIUM = ContentBlock(149, 1)
    ORE_WALL_THORIUM = ContentBlock(150, 1)
    ORE_WALL_BERYLLIUM = ContentBlock(151, 1)
    GRAPHITIC_WALL = ContentBlock(152, 1)
    ORE_WALL_TUNGSTEN = ContentBlock(153, 1)
    GRAPHITE_PRESS = ContentBlock(154, 2)
    MULTI_PRESS = ContentBlock(155, 3)
    SILICON_SMELTER = ContentBlock(156, 2)
    SILICON_CRUCIBLE = ContentBlock(157, 3)
    KILN = ContentBlock(158, 2)
    PLASTANIUM_COMPRESSOR = ContentBlock(159, 2)
    PHASE_WEAVER = ContentBlock(160, 2)
    SURGE_SMELTER = ContentBlock(161, 3)
    CRYOFLUID_MIXER = ContentBlock(162, 2)
    PYRATITE_MIXER = ContentBlock(163, 2)
    BLAST_MIXER = ContentBlock(164, 2)
    MELTER = ContentBlock(165, 1)
    SEPARATOR = ContentBlock(166, 2)
    DISASSEMBLER = ContentBlock(167, 3)
    SPORE_PRESS = ContentBlock(168, 2)
    PULVERIZER = ContentBlock(169, 1)
    COAL_CENTRIFUGE = ContentBlock(170, 2)
    INCINERATOR = ContentBlock(171, 1)
    SILICON_ARC_FURNACE = ContentBlock(172, 3)
    ELECTROLYZER = ContentBlock(173, 3)
    ATMOSPHERIC_CONCENTRATOR = ContentBlock(174, 3)
    OXIDATION_CHAMBER = ContentBlock(175, 3)
    ELECTRIC_HEATER = ContentBlock(176, 2)
    SLAG_HEATER = ContentBlock(177, 3)
    PHASE_HEATER = ContentBlock(178, 2)
    HEAT_REDIRECTOR = ContentBlock(179, 3)
    HEAT_ROUTER = ContentBlock(180, 3)
    SLAG_INCINERATOR = ContentBlock(181, 1)
    CARBIDE_CRUCIBLE = ContentBlock(182, 3)
    SLAG_CENTRIFUGE = ContentBlock(183, 3)
    SURGE_CRUCIBLE = ContentBlock(184, 3)
    CYANOGEN_SYNTHESIZER = ContentBlock(185, 3)
    PHASE_SYNTHESIZER = ContentBlock(186, 3)
    HEAT_REACTOR = ContentBlock(187, 3)
    COPPER_WALL = ContentBlock(188, 1)
    COPPER_WALL_LARGE = ContentBlock(189, 2)
    TITANIUM_WALL = ContentBlock(190, 1)
    TITANIUM_WALL_LARGE = ContentBlock(191, 2)
    PLASTANIUM_WALL = ContentBlock(192, 1)
    PLASTANIUM_WALL_LARGE = ContentBlock(193, 2)
    THORIUM_WALL = ContentBlock(194, 1)
    THORIUM_WALL_LARGE = ContentBlock(195, 2)
    PHASE_WALL = ContentBlock(196, 1)
    PHASE_WALL_LARGE = ContentBlock(197, 2)
    SURGE_WALL = ContentBlock(198, 1)
    SURGE_WALL_LARGE = ContentBlock(199, 2)
    DOOR = ContentBlock(200, 1)
    DOOR_LARGE = ContentBlock(201, 2)
    SCRAP_WALL = ContentBlock(202, 1)
    SCRAP_WALL_LARGE = ContentBlock(203, 2)
    SCRAP_WALL_HUGE = ContentBlock(204, 3)
    SCRAP_WALL_GIGANTIC = ContentBlock(205, 4)
    THRUSTER = ContentBlock(206, 4)
    BERYLLIUM_WALL = ContentBlock(207, 1)
    BERYLLIUM_WALL_LARGE = ContentBlock(208, 2)
    TUNGSTEN_WALL = ContentBlock(209, 1)
    TUNGSTEN_WALL_LARGE = ContentBlock(210, 2)
    BLAST_DOOR = ContentBlock(211, 2)
    REINFORCED_SURGE_WALL = ContentBlock(212, 1)
    REINFORCED_SURGE_WALL_LARGE = ContentBlock(213, 2)
    CARBIDE_WALL = ContentBlock(214, 1)
    CARBIDE_WALL_LARGE = ContentBlock(215, 2)
    SHIELDED_WALL = ContentBlock(216, 2)
    MENDER = ContentBlock(217, 1)
    MEND_PROJECTOR = ContentBlock(218, 2)
    OVERDRIVE_PROJECTOR = ContentBlock(219, 2)
    OVERDRIVE_DOME = ContentBlock(220, 3)
    FORCE_PROJECTOR = ContentBlock(221, 3)
    SHOCK_MINE = ContentBlock(222, 1)
    RADAR = ContentBlock(223, 1)
    BUILD_TOWER = ContentBlock(224, 3)
    REGEN_PROJECTOR = ContentBlock(225, 3)
    SHOCKWAVE_TOWER = ContentBlock(226, 3)
    SHIELD_PROJECTOR = ContentBlock(227, 3)
    LARGE_SHIELD_PROJECTOR = ContentBlock(228, 4)
    CONVEYOR = ContentBlock(229, 1)
    TITANIUM_CONVEYOR = ContentBlock(230, 1)
    PLASTANIUM_CONVEYOR = ContentBlock(231, 1)
    ARMORED_CONVEYOR = ContentBlock(232, 1)
    JUNCTION = ContentBlock(233, 1)
    BRIDGE_CONVEYOR = ContentBlock(234, 1)
    PHASE_CONVEYOR = ContentBlock(235, 1)
    SORTER = ContentBlock(236, 1)
    INVERTED_SORTER = ContentBlock(237, 1)
    ROUTER = ContentBlock(238, 1)
    DISTRIBUTOR = ContentBlock(239, 2)
    OVERFLOW_GATE = ContentBlock(240, 1)
    UNDERFLOW_GATE = ContentBlock(241, 1)
    MASS_DRIVER = ContentBlock(242, 3)
    DUCT = ContentBlock(243, 1)
    ARMORED_DUCT = ContentBlock(244, 1)
    DUCT_ROUTER = ContentBlock(245, 1)
    OVERFLOW_DUCT = ContentBlock(246, 1)
    UNDERFLOW_DUCT = ContentBlock(247, 1)
    DUCT_BRIDGE = ContentBlock(248, 1)
    DUCT_UNLOADER = ContentBlock(249, 1)
    SURGE_CONVEYOR = ContentBlock(250, 1)
    SURGE_ROUTER = ContentBlock(251, 1)
    UNIT_CARGO_LOADER = ContentBlock(252, 3)
    UNIT_CARGO_UNLOAD_POINT = ContentBlock(253, 2)
    MECHANICAL_PUMP = ContentBlock(254, 1)
    ROTARY_PUMP = ContentBlock(255, 2)
    IMPULSE_PUMP = ContentBlock(256, 3)
    CONDUIT = ContentBlock(257, 1)
    PULSE_CONDUIT = ContentBlock(258, 1)
    PLATED_CONDUIT = ContentBlock(259, 1)
    LIQUID_ROUTER = ContentBlock(260, 1)
    LIQUID_CONTAINER = ContentBlock(261, 2)
    LIQUID_TANK = ContentBlock(262, 3)
    LIQUID_JUNCTION = ContentBlock(263, 1)
    BRIDGE_CONDUIT = ContentBlock(264, 1)
    PHASE_CONDUIT = ContentBlock(265, 1)
    REINFORCED_PUMP = ContentBlock(266, 2)
    REINFORCED_CONDUIT = ContentBlock(267, 1)
    REINFORCED_LIQUID_JUNCTION = ContentBlock(268, 1)
    REINFORCED_BRIDGE_CONDUIT = ContentBlock(269, 1)
    REINFORCED_LIQUID_ROUTER = ContentBlock(270, 1)
    REINFORCED_LIQUID_CONTAINER = ContentBlock(271, 2)
    REINFORCED_LIQUID_TANK = ContentBlock(272, 3)
    POWER_NODE = ContentBlock(273, 1)
    POWER_NODE_LARGE = ContentBlock(274, 2)
    SURGE_TOWER = ContentBlock(275, 2)
    DIODE = ContentBlock(276, 1)
    BATTERY = ContentBlock(277, 1)
    BATTERY_LARGE = ContentBlock(278, 3)
    COMBUSTION_GENERATOR = ContentBlock(279, 1)
    THERMAL_GENERATOR = ContentBlock(280, 2)
    STEAM_GENERATOR = ContentBlock(281, 2)
    DIFFERENTIAL_GENERATOR = ContentBlock(282, 3)
    RTG_GENERATOR = ContentBlock(283, 2)
    SOLAR_PANEL = ContentBlock(284, 1)
    SOLAR_PANEL_LARGE = ContentBlock(285, 3)
    THORIUM_REACTOR = ContentBlock(286, 3)
    IMPACT_REACTOR = ContentBlock(287, 4)
    BEAM_NODE = ContentBlock(288, 1)
    BEAM_TOWER = ContentBlock(289, 3)
    BEAM_LINK = ContentBlock(290, 3)
    TURBINE_CONDENSER = ContentBlock(291, 3)
    CHEMICAL_COMBUSTION_CHAMBER = ContentBlock(292, 3)
    PYROLYSIS_GENERATOR = ContentBlock(293, 3)
    FLUX_REACTOR = ContentBlock(294, 5)
    NEOPLASIA_REACTOR = ContentBlock(295, 5)
    MECHANICAL_DRILL = ContentBlock(296, 2)
    PNEUMATIC_DRILL = ContentBlock(297, 2)
    LASER_DRILL = ContentBlock(298, 3)
    BLAST_DRILL = ContentBlock(299, 4)
    WATER_EXTRACTOR = ContentBlock(300, 2)
    CULTIVATOR = ContentBlock(301, 2)
    OIL_EXTRACTOR = ContentBlock(302, 3)
    VENT_CONDENSER = ContentBlock(303, 3)
    CLIFF_CRUSHER = ContentBlock(304, 2)
    PLASMA_BORE = ContentBlock(305, 2)
    LARGE_PLASMA_BORE = ContentBlock(306, 3)
    IMPACT_DRILL = ContentBlock(307, 4)
    ERUPTION_DRILL = ContentBlock(308, 5)
    CORE_SHARD = ContentBlock(309, 3)
    CORE_FOUNDATION = ContentBlock(310, 4)
    CORE_NUCLEUS = ContentBlock(311, 5)
    CORE_BASTION = ContentBlock(312, 4)
    CORE_CITADEL = ContentBlock(313, 5)
    CORE_ACROPOLIS = ContentBlock(314, 6)
    CONTAINER = ContentBlock(315, 2)
    VAULT = ContentBlock(316, 3)
    UNLOADER = ContentBlock(317, 1)
    REINFORCED_CONTAINER = ContentBlock(318, 2)
    REINFORCED_VAULT = ContentBlock(319, 3)
    DUO = ContentBlock(320, 1)
    SCATTER = ContentBlock(321, 2)
    SCORCH = ContentBlock(322, 1)
    HAIL = ContentBlock(323, 1)
    WAVE = ContentBlock(324, 2)
    LANCER = ContentBlock(325, 2)
    ARC = ContentBlock(326, 1)
    PARALLAX = ContentBlock(327, 2)
    SWARMER = ContentBlock(328, 2)
    SALVO = ContentBlock(329, 2)
    SEGMENT = ContentBlock(330, 2)
    TSUNAMI = ContentBlock(331, 3)
    FUSE = ContentBlock(332, 3)
    RIPPLE = ContentBlock(333, 3)
    CYCLONE = ContentBlock(334, 3)
    FORESHADOW = ContentBlock(335, 4)
    SPECTRE = ContentBlock(336, 4)
    MELTDOWN = ContentBlock(337, 4)
    BREACH = ContentBlock(338, 3)
    DIFFUSE = ContentBlock(339, 3)
    SUBLIMATE = ContentBlock(340, 3)
    TITAN = ContentBlock(341, 4)
    DISPERSE = ContentBlock(342, 4)
    AFFLICT = ContentBlock(343, 4)
    LUSTRE = ContentBlock(344, 4)
    SCATHE = ContentBlock(345, 4)
    SMITE = ContentBlock(346, 5)
    MALIGN = ContentBlock(347, 5)
    GROUND_FACTORY = ContentBlock(348, 3)
    AIR_FACTORY = ContentBlock(349, 3)
    NAVAL_FACTORY = ContentBlock(350, 3)
    ADDITIVE_RECONSTRUCTOR = ContentBlock(351, 3)
    MULTIPLICATIVE_RECONSTRUCTOR = ContentBlock(352, 5)
    EXPONENTIAL_RECONSTRUCTOR = ContentBlock(353, 7)
    TETRATIVE_RECONSTRUCTOR = ContentBlock(354, 9)
    REPAIR_POINT = ContentBlock(355, 1)
    REPAIR_TURRET = ContentBlock(356, 2)
    TANK_FABRICATOR = ContentBlock(357, 3)
    SHIP_FABRICATOR = ContentBlock(358, 3)
    MECH_FABRICATOR = ContentBlock(359, 3)
    TANK_REFABRICATOR = ContentBlock(360, 3)
    SHIP_REFABRICATOR = ContentBlock(361, 3)
    MECH_REFABRICATOR = ContentBlock(362, 3)
    PRIME_REFABRICATOR = ContentBlock(363, 5)
    TANK_ASSEMBLER = ContentBlock(364, 5)
    SHIP_ASSEMBLER = ContentBlock(365, 5)
    MECH_ASSEMBLER = ContentBlock(366, 5)
    BASIC_ASSEMBLER_MODULE = ContentBlock(367, 5)
    UNIT_REPAIR_TOWER = ContentBlock(368, 2)
    PAYLOAD_CONVEYOR = ContentBlock(369, 3)
    PAYLOAD_ROUTER = ContentBlock(370, 3)
    REINFORCED_PAYLOAD_CONVEYOR = ContentBlock(371, 3)
    REINFORCED_PAYLOAD_ROUTER = ContentBlock(372, 3)
    PAYLOAD_MASS_DRIVER = ContentBlock(373, 3)
    LARGE_PAYLOAD_MASS_DRIVER = ContentBlock(374, 5)
    SMALL_DECONSTRUCTOR = ContentBlock(375, 3)
    DECONSTRUCTOR = ContentBlock(376, 5)
    CONSTRUCTOR = ContentBlock(377, 3)
    LARGE_CONSTRUCTOR = ContentBlock(378, 5)
    PAYLOAD_LOADER = ContentBlock(379, 3)
    PAYLOAD_UNLOADER = ContentBlock(380, 3)
    POWER_SOURCE = ContentBlock(381, 1)
    POWER_VOID = ContentBlock(382, 1)
    ITEM_SOURCE = ContentBlock(383, 1)
    ITEM_VOID = ContentBlock(384, 1)
    LIQUID_SOURCE = ContentBlock(385, 1)
    LIQUID_VOID = ContentBlock(386, 1)
    PAYLOAD_SOURCE = ContentBlock(387, 5)
    PAYLOAD_VOID = ContentBlock(388, 5)
    HEAT_SOURCE = ContentBlock(389, 1)
    ILLUMINATOR = ContentBlock(390, 1)
    # LEGACY_MECH_PAD = ContentBlock(391, 1)
    # LEGACY_UNIT_FACTORY = ContentBlock(392, 1)
    # LEGACY_UNIT_FACTORY_AIR = ContentBlock(393, 1)
    # LEGACY_UNIT_FACTORY_GROUND = ContentBlock(394, 1)
    # COMMAND_CENTER = ContentBlock(395, 2)
    LAUNCH_PAD = ContentBlock(396, 3)
    INTERPLANETARY_ACCELERATOR = ContentBlock(397, 7)
    MESSAGE = ContentBlock(398, 1)
    SWITCH = ContentBlock(399, 1)
    MICRO_PROCESSOR = ContentBlock(400, 1)
    LOGIC_PROCESSOR = ContentBlock(401, 2)
    HYPER_PROCESSOR = ContentBlock(402, 3)
    MEMORY_CELL = ContentBlock(403, 1)
    MEMORY_BANK = ContentBlock(404, 2)
    LOGIC_DISPLAY = ContentBlock(405, 3)
    LARGE_LOGIC_DISPLAY = ContentBlock(406, 6)
    CANVAS = ContentBlock(407, 2)
    REINFORCED_MESSAGE = ContentBlock(408, 1)
    WORLD_PROCESSOR = ContentBlock(409, 1)
    WORLD_CELL = ContentBlock(410, 1)
    WORLD_MESSAGE = ContentBlock(411, 1)
    WORLD_SWITCH = ContentBlock(412, 1)

    DAGGER = ContentType(ContentTypes.UNIT, 0)
    MACE = ContentType(ContentTypes.UNIT, 1)
    FORTRESS = ContentType(ContentTypes.UNIT, 2)
    SCEPTER = ContentType(ContentTypes.UNIT, 3)
    REIGN = ContentType(ContentTypes.UNIT, 4)
    NOVA = ContentType(ContentTypes.UNIT, 5)
    PULSAR = ContentType(ContentTypes.UNIT, 6)
    QUASAR = ContentType(ContentTypes.UNIT, 7)
    VELA = ContentType(ContentTypes.UNIT, 8)
    CORVUS = ContentType(ContentTypes.UNIT, 9)
    CRAWLER = ContentType(ContentTypes.UNIT, 10)
    ATRAX = ContentType(ContentTypes.UNIT, 11)
    SPIROCT = ContentType(ContentTypes.UNIT, 12)
    ARKYID = ContentType(ContentTypes.UNIT, 13)
    TOXOPID = ContentType(ContentTypes.UNIT, 14)
    FLARE = ContentType(ContentTypes.UNIT, 15)
    HORIZON = ContentType(ContentTypes.UNIT, 16)
    ZENITH = ContentType(ContentTypes.UNIT, 17)
    ANTUMBRA = ContentType(ContentTypes.UNIT, 18)
    ECLIPSE = ContentType(ContentTypes.UNIT, 19)
    MONO = ContentType(ContentTypes.UNIT, 20)
    POLY = ContentType(ContentTypes.UNIT, 21)
    MEGA = ContentType(ContentTypes.UNIT, 22)
    QUAD = ContentType(ContentTypes.UNIT, 23)
    OCT = ContentType(ContentTypes.UNIT, 24)
    RISSO = ContentType(ContentTypes.UNIT, 25)
    MINKE = ContentType(ContentTypes.UNIT, 26)
    BRYDE = ContentType(ContentTypes.UNIT, 27)
    SEI = ContentType(ContentTypes.UNIT, 28)
    OMURA = ContentType(ContentTypes.UNIT, 29)
    RETUSA = ContentType(ContentTypes.UNIT, 30)
    OXYNOE = ContentType(ContentTypes.UNIT, 31)
    CYERCE = ContentType(ContentTypes.UNIT, 32)
    AEGIRES = ContentType(ContentTypes.UNIT, 33)
    NAVANAX = ContentType(ContentTypes.UNIT, 34)
    ALPHA = ContentType(ContentTypes.UNIT, 35)
    BETA = ContentType(ContentTypes.UNIT, 36)
    GAMMA = ContentType(ContentTypes.UNIT, 37)
    STELL = ContentType(ContentTypes.UNIT, 38)
    LOCUS = ContentType(ContentTypes.UNIT, 39)
    PRECEPT = ContentType(ContentTypes.UNIT, 40)
    VANQUISH = ContentType(ContentTypes.UNIT, 41)
    CONCUER = ContentType(ContentTypes.UNIT, 42)
    MERUI = ContentType(ContentTypes.UNIT, 43)
    CLEROI = ContentType(ContentTypes.UNIT, 44)
    ANTHICUS = ContentType(ContentTypes.UNIT, 45)
    TECTA = ContentType(ContentTypes.UNIT, 46)
    COLLARIS = ContentType(ContentTypes.UNIT, 47)
    ELUDE = ContentType(ContentTypes.UNIT, 48)
    AVERT = ContentType(ContentTypes.UNIT, 49)
    OBVIATE = ContentType(ContentTypes.UNIT, 50)
    QUELL = ContentType(ContentTypes.UNIT, 51)
    DISRUPT = ContentType(ContentTypes.UNIT, 52)
    RENALE = ContentType(ContentTypes.UNIT, 53)
    LATUM = ContentType(ContentTypes.UNIT, 54)
    EVOKE = ContentType(ContentTypes.UNIT, 55)
    INCITE = ContentType(ContentTypes.UNIT, 56)
    EMANATE = ContentType(ContentTypes.UNIT, 57)
    BLOCK = ContentType(ContentTypes.UNIT, 58)
    MANIFOLD = ContentType(ContentTypes.UNIT, 59)
    ASSEMBLY_DRONE = ContentType(ContentTypes.UNIT, 60)

    WATER = ContentType(ContentTypes.LIQUID, 0)
    SLAG = ContentType(ContentTypes.LIQUID, 1)
    OIL = ContentType(ContentTypes.LIQUID, 2)
    CRYOFLUID = ContentType(ContentTypes.LIQUID, 3)
    ARKYCITE = ContentType(ContentTypes.LIQUID, 4)
    GALLIUM = ContentType(ContentTypes.LIQUID, 5)
    NEOPLASM = ContentType(ContentTypes.LIQUID, 6)
    ZONE = ContentType(ContentTypes.LIQUID, 7)
    HYDROGEN = ContentType(ContentTypes.LIQUID, 8)
    NITROGEN = ContentType(ContentTypes.LIQUID, 9)
    CYANOGEN = ContentType(ContentTypes.LIQUID, 10)

class ContentLists:
        BLOCKS = list[Content]()
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
            elif(content.value.type == ContentTypes.ITEM):
                ITEMS.append(content)
            elif(content.value.type == ContentTypes.UNIT):
                UNITS.append(content)
            elif(content.value.type == ContentTypes.LIQUID):
                LIQUIDS.append(content)
        BUILDINGS = [Content.GRAPHITE_PRESS, Content.MULTI_PRESS, Content.SILICON_SMELTER, Content.SILICON_CRUCIBLE, Content.KILN, Content.PLASTANIUM_COMPRESSOR, Content.PHASE_WEAVER, Content.SURGE_SMELTER, Content.CRYOFLUID_MIXER, Content.PYRATITE_MIXER, Content.BLAST_MIXER, Content.MELTER, Content.SEPARATOR, Content.DISASSEMBLER, Content.SPORE_PRESS, Content.PULVERIZER, Content.COAL_CENTRIFUGE, Content.INCINERATOR, Content.SILICON_ARC_FURNACE, Content.ELECTROLYZER, Content.ATMOSPHERIC_CONCENTRATOR, Content.OXIDATION_CHAMBER, Content.ELECTRIC_HEATER, Content.SLAG_HEATER, Content.PHASE_HEATER, Content.HEAT_REDIRECTOR, Content.HEAT_ROUTER, Content.SLAG_INCINERATOR, Content.CARBIDE_CRUCIBLE, Content.SLAG_CENTRIFUGE, Content.SURGE_CRUCIBLE, Content.CYANOGEN_SYNTHESIZER, Content.PHASE_SYNTHESIZER, Content.HEAT_REACTOR, Content.COPPER_WALL, Content.COPPER_WALL_LARGE, Content.TITANIUM_WALL, Content.TITANIUM_WALL_LARGE, Content.PLASTANIUM_WALL, Content.PLASTANIUM_WALL_LARGE, Content.THORIUM_WALL, Content.THORIUM_WALL_LARGE, Content.PHASE_WALL, Content.PHASE_WALL_LARGE, Content.SURGE_WALL, Content.SURGE_WALL_LARGE, Content.DOOR, Content.DOOR_LARGE, Content.SCRAP_WALL, Content.SCRAP_WALL_LARGE, Content.SCRAP_WALL_HUGE, Content.SCRAP_WALL_GIGANTIC, Content.THRUSTER, Content.BERYLLIUM_WALL, Content.BERYLLIUM_WALL_LARGE, Content.TUNGSTEN_WALL, Content.TUNGSTEN_WALL_LARGE, Content.BLAST_DOOR, Content.REINFORCED_SURGE_WALL, Content.REINFORCED_SURGE_WALL_LARGE, Content.CARBIDE_WALL, Content.CARBIDE_WALL_LARGE, Content.SHIELDED_WALL, Content.MENDER, Content.MEND_PROJECTOR, Content.OVERDRIVE_PROJECTOR, Content.OVERDRIVE_DOME, Content.FORCE_PROJECTOR, Content.SHOCK_MINE, Content.RADAR, Content.BUILD_TOWER, Content.REGEN_PROJECTOR, Content.SHOCKWAVE_TOWER, Content.SHIELD_PROJECTOR, Content.LARGE_SHIELD_PROJECTOR, Content.CONVEYOR, Content.TITANIUM_CONVEYOR, Content.PLASTANIUM_CONVEYOR, Content.ARMORED_CONVEYOR, Content.JUNCTION, Content.BRIDGE_CONVEYOR, Content.PHASE_CONVEYOR, Content.SORTER, Content.INVERTED_SORTER, Content.ROUTER, Content.DISTRIBUTOR, Content.OVERFLOW_GATE, Content.UNDERFLOW_GATE, Content.MASS_DRIVER, Content.DUCT, Content.ARMORED_DUCT, Content.DUCT_ROUTER, Content.OVERFLOW_DUCT, Content.UNDERFLOW_DUCT, Content.DUCT_BRIDGE, Content.DUCT_UNLOADER, Content.SURGE_CONVEYOR, Content.SURGE_ROUTER, Content.UNIT_CARGO_LOADER, Content.UNIT_CARGO_UNLOAD_POINT, Content.MECHANICAL_PUMP, Content.ROTARY_PUMP, Content.IMPULSE_PUMP, Content.CONDUIT, Content.PULSE_CONDUIT, Content.PLATED_CONDUIT, Content.LIQUID_ROUTER, Content.LIQUID_CONTAINER, Content.LIQUID_TANK, Content.LIQUID_JUNCTION, Content.BRIDGE_CONDUIT, Content.PHASE_CONDUIT, Content.REINFORCED_PUMP, Content.REINFORCED_CONDUIT, Content.REINFORCED_LIQUID_JUNCTION, Content.REINFORCED_BRIDGE_CONDUIT, Content.REINFORCED_LIQUID_ROUTER, Content.REINFORCED_LIQUID_CONTAINER, Content.REINFORCED_LIQUID_TANK, Content.POWER_NODE, Content.POWER_NODE_LARGE, Content.SURGE_TOWER, Content.DIODE, Content.BATTERY, Content.BATTERY_LARGE, Content.COMBUSTION_GENERATOR, Content.THERMAL_GENERATOR, Content.STEAM_GENERATOR, Content.DIFFERENTIAL_GENERATOR, Content.RTG_GENERATOR, Content.SOLAR_PANEL, Content.SOLAR_PANEL_LARGE, Content.THORIUM_REACTOR, Content.IMPACT_REACTOR, Content.BEAM_NODE, Content.BEAM_TOWER, Content.BEAM_LINK, Content.TURBINE_CONDENSER, Content.CHEMICAL_COMBUSTION_CHAMBER, Content.PYROLYSIS_GENERATOR, Content.FLUX_REACTOR, Content.NEOPLASIA_REACTOR, Content.MECHANICAL_DRILL, Content.PNEUMATIC_DRILL, Content.LASER_DRILL, Content.BLAST_DRILL, Content.WATER_EXTRACTOR, Content.CULTIVATOR, Content.OIL_EXTRACTOR, Content.VENT_CONDENSER, Content.CLIFF_CRUSHER, Content.PLASMA_BORE, Content.LARGE_PLASMA_BORE, Content.IMPACT_DRILL, Content.ERUPTION_DRILL, Content.CORE_SHARD, Content.CORE_FOUNDATION, Content.CORE_NUCLEUS, Content.CORE_BASTION, Content.CORE_CITADEL, Content.CORE_ACROPOLIS, Content.CONTAINER, Content.VAULT, Content.UNLOADER, Content.REINFORCED_CONTAINER, Content.REINFORCED_VAULT, Content.DUO, Content.SCATTER, Content.SCORCH, Content.HAIL, Content.WAVE, Content.LANCER, Content.ARC, Content.PARALLAX, Content.SWARMER, Content.SALVO, Content.SEGMENT, Content.TSUNAMI, Content.FUSE, Content.RIPPLE, Content.CYCLONE, Content.FORESHADOW, Content.SPECTRE, Content.MELTDOWN, Content.BREACH, Content.DIFFUSE, Content.SUBLIMATE, Content.TITAN, Content.DISPERSE, Content.AFFLICT, Content.LUSTRE, Content.SCATHE, Content.SMITE, Content.MALIGN, Content.GROUND_FACTORY, Content.AIR_FACTORY, Content.NAVAL_FACTORY, Content.ADDITIVE_RECONSTRUCTOR, Content.MULTIPLICATIVE_RECONSTRUCTOR, Content.EXPONENTIAL_RECONSTRUCTOR, Content.TETRATIVE_RECONSTRUCTOR, Content.REPAIR_POINT, Content.REPAIR_TURRET, Content.TANK_FABRICATOR, Content.SHIP_FABRICATOR, Content.MECH_FABRICATOR, Content.TANK_REFABRICATOR, Content.SHIP_REFABRICATOR, Content.MECH_REFABRICATOR, Content.PRIME_REFABRICATOR, Content.TANK_ASSEMBLER, Content.SHIP_ASSEMBLER, Content.MECH_ASSEMBLER, Content.BASIC_ASSEMBLER_MODULE, Content.UNIT_REPAIR_TOWER, Content.PAYLOAD_CONVEYOR, Content.PAYLOAD_ROUTER, Content.REINFORCED_PAYLOAD_CONVEYOR, Content.REINFORCED_PAYLOAD_ROUTER, Content.PAYLOAD_MASS_DRIVER, Content.LARGE_PAYLOAD_MASS_DRIVER, Content.SMALL_DECONSTRUCTOR, Content.DECONSTRUCTOR, Content.CONSTRUCTOR, Content.LARGE_CONSTRUCTOR, Content.PAYLOAD_LOADER, Content.PAYLOAD_UNLOADER, Content.POWER_SOURCE, Content.POWER_VOID, Content.ITEM_SOURCE, Content.ITEM_VOID, Content.LIQUID_SOURCE, Content.LIQUID_VOID, Content.PAYLOAD_SOURCE, Content.PAYLOAD_VOID, Content.HEAT_SOURCE, Content.ILLUMINATOR, Content.LAUNCH_PAD, Content.INTERPLANETARY_ACCELERATOR, Content.MESSAGE, Content.SWITCH, Content.MICRO_PROCESSOR, Content.LOGIC_PROCESSOR, Content.HYPER_PROCESSOR, Content.MEMORY_CELL, Content.MEMORY_BANK, Content.LOGIC_DISPLAY, Content.LARGE_LOGIC_DISPLAY, Content.CANVAS, Content.REINFORCED_MESSAGE, Content.WORLD_PROCESSOR, Content.WORLD_CELL, Content.WORLD_MESSAGE, Content.WORLD_SWITCH]

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