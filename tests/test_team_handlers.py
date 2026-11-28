"""Pinned inert source snapshots + actual native Runner on synthetic arrays.

No source import/evaluation, network, credentials, live devices, or approvals.
Only temporary YAML files are written by these tests. The audited source and
needed numeric resources are embedded below to keep tests portable in two files.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path

import pytest

from helpers import blank, paint_points
from test_handler_runner import run_synthetic
from test_handlers import case, handler
import onmyoji_agentflow.convert.team_handlers as team
from onmyoji_agentflow.convert.handlers import UnsupportedHandler
from onmyoji_agentflow.convert.jsliteral import extract_literal_after, find_consts, parse
from onmyoji_agentflow.workflow.schema import load_workflow
from onmyoji_agentflow.yamlio import dump_yaml


AUDITED = json.loads(r'''{
  "license": "MIT License\n\nCopyright (c) 2019 Chaos\n\nPermission is hereby granted, free of charge, to any person obtaining a copy\nof this software and associated documentation files (the \"Software\"), to deal\nin the Software without restriction, including without limitation the rights\nto use, copy, modify, merge, publish, distribute, sublicense, and/or sell\ncopies of the Software, and to permit persons to whom the Software is\nfurnished to do so, subject to the following conditions:\n\nThe above copyright notice and this permission notice shall be included in all\ncopies or substantial portions of the Software.\n\nTHE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\nIMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\nFITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\nAUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\nLIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\nOUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\nSOFTWARE.\n",
  "sources": {
    "4": "import { Script } from '@/system/script';\nimport { IFuncOrigin, IFuncOperatorOrigin, IFuncOperator } from '@/interface/IFunc';\n\n// const normal = -1; //定义常量\nconst left = 0;\nconst center = 1;\nconst right = 2;\n\nexport class Func004 implements IFuncOrigin {\n\tid = 4;\n\tname = '接受邀请';\n\tdesc = '左侧弹出邀请提示时，自动接受邀请';\n\tconfig = [{\n\t\tdesc: '',\n\t\tconfig: [{\n\t\t\tname: 'teammate_exit',\n\t\t\tdesc: '队长退出后切换方案',\n\t\t\ttype: 'switch',\n\t\t\tdefault: true,\n\t\t}, {\n\t\t\tname: 'teammate_exit_next_scheme',\n\t\t\tdesc: '下一个方案',\n\t\t\ttype: 'scheme',\n\t\t\tdefault: '关闭BUFF',\n\t\t}, {\n\t\t\tname: 'auto_team',\n\t\t\tdesc: '自动接受后不再处理接受邀请',\n\t\t\ttype: 'switch',\n\t\t\tdefault: false,\n\t\t},]\n\t}]\n\toperator: IFuncOperatorOrigin[] = [{\n\t\t// 0 自动接受邀请\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[left, 20, 254, 0x7e6750],\n\t\t\t\t[left, 45, 248, 0xdf6e5b],\n\t\t\t\t[left, 138, 260, 0x57b260],\n\t\t\t\t[left, 234, 251, 0xefc791],\n\t\t\t\t[left, 247, 269, 0x59b462],\n\t\t\t\t[left, 255, 276, 0x86705d],\n\t\t\t\t[left, 192, 276, 0xeadece]]\n\t\t],\n\t\toper: [\n\t\t\t[left, 1280, 720, 219, 237, 254, 275, 600]\n\t\t]\n\t}, { // 1 接受一次邀请\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[left, 128, 255, 0x58b361],\n\t\t\t\t[left, 45, 257, 0xdd6a59],\n\t\t\t\t[left, 79, 222, 0xe3d3c2],\n\t\t\t\t[left, 14, 299, 0xf1be36],\n\t\t\t\t[left, 176, 291, 0xefe5d6],\n\t\t\t\t[center, 507, 273, 0xe7d8c2],\n\t\t\t\t[center, 442, 233, 0xece0d1]\n\t\t\t]\n\t\t],\n\t\toper: [\n\t\t\t[left, 1280, 720, 120, 239, 159, 273, 600]\n\t\t]\n\t}, { // 2\t挑战_亮\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[left, 43, 37, 0xf5e6a8],\n\t\t\t\t[right, 1177, 667, 0xd8b871],\n\t\t\t\t[right, 1187, 679, 0xcda35d],\n\t\t\t\t[right, 1188, 609, 0xf1e096],\n\t\t\t\t[left, 60, 39, 0x84582f],\n\t\t\t\t[left, 19, 47, 0x281717]\n\t\t\t]\n\t\t],\n\t}, { // 3\t挑战_暗\n\t\tdesc: [\n\t\t\t1280, 720,\n\t\t\t[\n\t\t\t\t[left, 43, 37, 0xf5e6a8],\n\t\t\t\t[right, 1210, 621, 0xd9d9d9],\n\t\t\t\t[right, 1228, 658, 0xc8c8c8],\n\t\t\t\t[left, 60, 39, 0x84582f],\n\t\t\t\t[left, 19, 47, 0x281717]\n\t\t\t]\n\t\t],\n\t}, { // 4 组队有探索奖励\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[left, 11, 132, 0x49352f],\n\t\t\t\t[left, 61, 132, 0x49352f],\n\t\t\t\t[left, 119, 132, 0x49352f],\n\t\t\t\t[left, 19, 159, 0xe8d8bc],\n\t\t\t]\n\t\t],\n\t},];\n\toperatorFunc(thisScript: Script, thisOperator: IFuncOperator[]): boolean {\n\t\tconst thisConf = thisScript.scheme.config['4'];\n\t\tif (thisScript.oper({\n\t\t\tname: '组队界面奖励检测',\n\t\t\toperator: [{ desc: thisOperator[4].desc }]\n\t\t})) {\n\t\t\tconst point = thisScript.findMultiColor('组队探索_宝箱');\n\t\t\tif (point) {\n\t\t\t\tconst oper = [[point.x, point.y, point.x + 5, point.y + 5, 500]];\n\t\t\t\tthisScript.regionClick(oper);\n\t\t\t\treturn true;\n\t\t\t}\n\t\t}\n\t\tif (thisConf && thisConf.teammate_exit && thisScript.oper({\n\t\t\tid: 4,\n\t\t\tname: '队长退出',\n\t\t\toperator: [thisOperator[2], thisOperator[3]]\n\t\t})) {\n\t\t\tthisScript.rerun(thisConf.teammate_exit_next_scheme);\n\t\t\tsleep(3000)\n\t\t\treturn true;\n\t\t}\n\t\tif (thisConf && thisConf.auto_team && thisScript.global.yaoqing_close) {\n\t\t\treturn false;\n\t\t}\n\t\tif (thisScript.oper({\n\t\t\tid: 4,\n\t\t\tname: '接受邀请',\n\t\t\toperator: [thisOperator[0]]\n\t\t})) {\n\t\t\tthisScript.global.yaoqing_close = true;\n\t\t\treturn true;\n\t\t}\n\t\tif (thisScript.oper({\n\t\t\tid: 4,\n\t\t\tname: '接受邀请',\n\t\t\toperator: [thisOperator[1]]\n\t\t})) {\n\t\t\treturn true;\n\t\t}\n\t}\n}\n",
    "5": "import { Script } from '@/system/script';\nimport { IFuncOrigin, IFuncOperatorOrigin, IFuncOperator } from '@/interface/IFunc';\n\n// const normal = -1; //定义常量\nconst left = 0;\nconst center = 1;\nconst right = 2;\n\nexport class Func005 implements IFuncOrigin {\n\tid = 5;\n\tname = '组队挑战';\n\tdesc = '在组队界面时，点击挑战按钮，可配置三人开始或有人就开';\n\tconfig = [{\n\t\tdesc: '',\n\t\tconfig: [{\n\t\t\tname: 'type',\n\t\t\tdesc: '组队挑战',\n\t\t\ttype: 'list',\n\t\t\tdata: ['有人就开', '三人'],\n\t\t\tdefault: '有人就开',\n\t\t}]\n\t}];\n\toperator: IFuncOperatorOrigin[] = [{ // 组队界面_挑战亮\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[left, 42, 38, 0xf7eaac],\n\t\t\t\t[right, 1177, 667, 0xd8b871],\n\t\t\t\t[right, 1187, 679, 0xcda35d],\n\t\t\t\t[right, 1188, 609, 0xf1e096],\n\t\t\t\t[left, 60, 39, 0x84582f],\n\t\t\t\t[left, 19, 47, 0x281717]\n\t\t\t]\n\t\t],\n\t}, {\n\t\tdesc: [1280, 720,\n\t\t\t[[right, 645, 270, 0xfffefc]]\n\t\t]\n\t}, {\n\t\tdesc: [1280, 720,\n\t\t\t[[right, 1064, 252, 0xfffffe]]\n\t\t]\n\t}, {\n\t\toper: [\n\t\t\t[right, 1280, 720, 1192, 613, 1251, 677, 2000]\n\t\t]\n\t}, {\n\t\t// 永生之海\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[right, 1199, 608, 0xe6dac6],\n\t\t\t\t[left, 29, 39, 0x1f160e],\n\t\t\t\t[left, 55, 45, 0xd7c5a2],\n\t\t\t\t[left, 126, 43, 0xd7c5a2],\n\t\t\t\t[center, 654, 306, 0xeae1e2],\n\t\t\t\t[center, 633, 327, 0xfdfbf9],\n\t\t\t\t[center, 636, 309, 0x413f53],\n\t\t\t\t[center, 655, 323, 0x343244],\n\t\t\t\t[right, 1170, 587, 0x604030]\n\t\t\t]\n\t\t],\n\t\toper: [\n\t\t\t[right, 1280, 720, 1168, 598, 1250, 678, 2000]\n\t\t]\n\t}, { // 5 金币/经验妖怪界面_有人进入\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[center, 420, 310, 0xfffefc],\n\t\t\t]\n\t\t],\n\t}, { // 6 金币/经验妖怪界面_10秒无人进入_退出\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[center, 544, 29, 0xb38e57],\n\t\t\t\t[center, 556, 29, 0xcc9e5b],\n\t\t\t\t[center, 597, 29, 0xd2a25c],\n\t\t\t\t[center, 590, 29, 0xa6824c],\n\t\t\t]\n\t\t],\n\t\toper: [\n\t\t\t[center, 1280, 720, 35, 24, 66, 53, 1000],\n\t\t]\n\t}, { // 7 金币/经验组队界面\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[left, 59, 644, 0xf8f3e0],\n\t\t\t\t[left, 45, 645, 0xf8f3e0],\n\t\t\t\t[left, 43, 664, 0xf5f0db],\n\t\t\t\t[left, 53, 672, 0x614231],\n\t\t\t\t[left, 75, 694, 0x291c14],\n\t\t\t\t[left, 26, 688, 0x322c1f],\n\t\t\t]\n\t\t],\n\t}, { // 8 组队有探索奖励\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[left, 11, 132, 0x49352f],\n\t\t\t\t[left, 61, 132, 0x49352f],\n\t\t\t\t[left, 119, 132, 0x49352f],\n\t\t\t\t[left, 19, 159, 0xe8d8bc],\n\t\t\t]\n\t\t],\n\t},];\n\t// 0-有人就开，1-第一个+号上的点，2-第二个+号上的点，如果1或者2任意一个匹配上了，说明人没满\n\toperatorFunc(thisScript: Script, thisOperator: IFuncOperator[]): boolean {\n\t\tif (thisScript.oper({\n\t\t\tname: '组队界面奖励检测',\n\t\t\toperator: [{ desc: thisOperator[8].desc }]\n\t\t})) {\n\t\t\tconst point = thisScript.findMultiColor('组队探索_宝箱');\n\t\t\tif (point) {\n\t\t\t\tconst oper = [[point.x, point.y, point.x + 5, point.y + 5, 500]];\n\t\t\t\tthisScript.regionClick(oper);\n\t\t\t\treturn true;\n\t\t\t}\n\t\t}\n\t\tif (thisScript.oper({\n\t\t\tname: '组队挑战_永生之海_判断',\n\t\t\toperator: [thisOperator[4]]\n\t\t}, 0)) {\n\t\t\treturn true;\n\t\t}\n\t\tif (thisScript.oper({\n\t\t\tname: '组队挑战_判断',\n\t\t\toperator: [{ desc: thisOperator[0].desc }]\n\t\t}, 0)) {\n\t\t\tconst thisconf = thisScript.scheme.config['5']; // 获取配置\n\t\t\tif (thisconf.type === '有人就开') {\n\t\t\t\tif (thisScript.oper({\n\t\t\t\t\tname: '金币/经验',\n\t\t\t\t\toperator: [thisOperator[7]]\n\t\t\t\t})) {\n\t\t\t\t\tif (!thisScript.oper({\n\t\t\t\t\t\tname: '金币/经验妖怪有人再开',\n\t\t\t\t\t\toperator: [thisOperator[5]]\n\t\t\t\t\t})) {\n\t\t\t\t\t\tthisScript.regionClick(thisOperator[3].oper);\n\t\t\t\t\t\treturn true;\n\t\t\t\t\t}\n\t\t\t\t\tif (thisScript.oper({\n\t\t\t\t\t\tname: '10秒无人进入_退出',\n\t\t\t\t\t\toperator: [thisOperator[6]]\n\t\t\t\t\t})) {\n\t\t\t\t\t\treturn true;\n\t\t\t\t\t}\n\t\t\t\t} else {\n\t\t\t\t\tif (!thisScript.oper({\n\t\t\t\t\t\tname: '二号位',\n\t\t\t\t\t\toperator: [thisOperator[1]]\n\t\t\t\t\t})) {\n\t\t\t\t\t\tif (thisScript.oper({\n\t\t\t\t\t\t\tname: '组队界面奖励检测',\n\t\t\t\t\t\t\toperator: [{ desc: thisOperator[8].desc }]\n\t\t\t\t\t\t})) {\n\t\t\t\t\t\t\tsleep(2000);\n\t\t\t\t\t\t}\n\t\t\t\t\t\tthisScript.regionClick(thisOperator[3].oper);\n\t\t\t\t\t\treturn true;\n\t\t\t\t\t}\n\t\t\t\t}\n\n\t\t\t} else if (thisconf.type === '三人') {\n\t\t\t\tif (!thisScript.oper({\n\t\t\t\t\tname: '组队挑战_乘客1无人',\n\t\t\t\t\toperator: [thisOperator[1]]\n\t\t\t\t}, 0) && !thisScript.oper({\n\t\t\t\t\tname: '组队挑战_乘客2无人',\n\t\t\t\t\toperator: [thisOperator[2]]\n\t\t\t\t}, 0)) {\n\t\t\t\t\tthisScript.regionClick(thisOperator[3].oper);\n\t\t\t\t\treturn true;\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\t\treturn false;\n\t}\n}\n\nexport default new Func005();",
    "6": "import { Script } from '@/system/script';\nimport { IFuncOrigin, IFuncOperatorOrigin, IFuncOperator } from '@/interface/IFunc';\n// const normal = -1; //定义常量\n// const left = 0;\nconst center = 1;\nconst right = 2;\n\nexport class Func006 implements IFuncOrigin {\n\tid = 6;\n\tname = '御魂/御灵/秘闻挑战';\n\tdesc = '点击挑战按钮，连续点击3次后未开始将自动停止脚本';\n\tconfig = [{\n\t\tdesc: '',\n\t\tconfig: [{\n\t\t\tname: 'next_scheme',\n\t\t\tdesc: '下一个方案',\n\t\t\ttype: 'scheme',\n\t\t\tdefault: '__停止脚本__',\n\t\t}]\n\t}];\n\toperator: IFuncOperatorOrigin[] = [{\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[right, 1011, 595, 0xe3d7c2],\n\t\t\t\t[right, 1012, 668, 0xe7dac3],\n\t\t\t\t[right, 964, 591, 0x543825],\n\t\t\t\t[right, 1149, 585, 0x5b3d2d],\n\t\t\t\t[right, 1188, 588, 0xe2d5c1],\n\t\t\t\t[right, 1153, 679, 0x392418],\n\t\t\t]\n\t\t],\n\t\toper: [\n\t\t\t[center, 1280, 720, 1148, 602, 1235, 663, 1000],\n\t\t]\n\t}, { // 1 御灵\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[right, 1059, 583, 0x5d402e],\n\t\t\t\t[right, 1095, 592, 0xe1d6c0],\n\t\t\t\t[right, 1140, 586, 0x553b2c],\n\t\t\t\t[right, 1056, 673, 0x392318],\n\t\t\t\t[right, 1100, 676, 0xe3d9c2],\n\t\t\t]\n\t\t],\n\t\toper: [\n\t\t\t[center, 1280, 720, 1055, 595, 1143, 669, 1000],\n\t\t]\n\t}, { // 2 普通秘闻\n\t\tdesc: [1280, 720,\n\t\t\t[\n\t\t\t\t[right, 1056, 566, 0x533522],\n\t\t\t\t[right, 1144, 564, 0x59392a],\n\t\t\t\t[right, 1064, 606, 0xe3d7c2],\n\t\t\t\t[right, 1142, 605, 0xe5d9c4],\n\t\t\t\t[right, 1059, 651, 0x392418],\n\t\t\t]\n\t\t],\n\t\toper: [\n\t\t\t[center, 1280, 720, 1052, 568, 1153, 648, 1000],\n\t\t]\n\t},];\n\toperatorFunc(thisScript: Script, thisOperator: IFuncOperator[]): boolean {\n\t\tconst thisconf = thisScript.scheme.config['6'];\n\t\tlet curCnt = 0;\n\t\tconst maxCount = 3;\n\t\twhile (thisScript.oper({\n\t\t\tid: 6,\n\t\t\tname: '御魂/御灵挑战',\n\t\t\toperator: [thisOperator[0], thisOperator[1], thisOperator[2]]\n\t\t}, 0)) {\n\t\t\tcurCnt++;\n\t\t\tthisScript.keepScreen(false);\n\t\t\tif (curCnt >= maxCount) {\n\t\t\t\tthisScript.myToast(`连续执行${maxCount}次挑战后未开始，脚本自动停止`);\n\t\t\t\tthisScript.rerun(thisconf.next_scheme);\n\t\t\t\tsleep(2000);\n\t\t\t\treturn false;\n\t\t\t}\n\t\t}\n\t\tif (curCnt) {\n\t\t\treturn true;\n\t\t}\n\t\treturn false;\n\t}\n}\n\nexport default new Func006();\n",
    "40": "import { IFuncOrigin, IFuncOperatorOrigin, IFuncOperator } from '@/interface/IFunc';\nimport { Script } from '@/system/script';\n// const normal = -1; //定义常量\nconst left = 0;\nconst center = 1;\n// const right = 2;\n\nexport class Func040 implements IFuncOrigin {\n\tid = 40;\n\tname = '关闭BUFF';\n\tconfig = [{\n\t\tdesc: '结束后切换方案',\n\t\tconfig: [{\n\t\t\tname: 'scheme_switch_enabled',\n\t\t\tdesc: '是否启用',\n\t\t\ttype: 'switch',\n\t\t\tdefault: false,\n\t\t}, {\n\t\t\tname: 'next_scheme',\n\t\t\tdesc: '下一个方案',\n\t\t\ttype: 'scheme',\n\t\t\tdefault: '返回庭院',\n\t\t}]\n\t}, {\n\t\tdesc: '准备界面下关闭buff',\n\t\tconfig: [{\n\t\t\tname: 'ready_once_buff',\n\t\t\tdesc: '是否在准备界面下关闭buff，运行一次后不再运行，启用需将本功能排在“001准备”前',\n\t\t\ttype: 'switch',\n\t\t\tdefault: false,\n\t\t}]\n\t}];\n\toperator: IFuncOperatorOrigin[] = [{\n\t\t// 0 已适配66 buff界面\n\t\tdesc: 'BUFF界面',\n\t\toper: [\n\t\t\t[center, 1280, 720, 0, 0, 855 - 782, 431 - 415, 2000],\n\t\t\t[center, 1280, 720, 110, 120, 338, 549, 500],\n\t\t]\n\t}, {\n\t\t// 1 准备界面\n\t\tdesc: '准备界面_未准备',\n\t\toper: [\n\t\t\t[left, 1280, 720, 119, 659, 150, 712, 1000],\n\t\t]\n\t}];\n\toperatorFunc(thisScript: Script, thisOperator: IFuncOperator[]): boolean {\n\t\tconst thisconf = thisScript.scheme.config['40'];\n\t\tif (thisScript.oper({\n\t\t\tid: 40,\n\t\t\tname: 'BUFF界面',\n\t\t\toperator: [{\n\t\t\t\tdesc: thisOperator[0].desc\n\t\t\t}]\n\t\t})) {\n\t\t\tthisScript.global.closed_buff = true;\n\t\t\t// 金币妖怪_判断挑战次数是否用完\n\t\t\tconst point = thisScript.findMultiColor('开启的BUFF') || null\n\t\t\tif (point) {\n\t\t\t\tthisScript.regionClick([\n\t\t\t\t\t[point.x, point.y, point.x + thisOperator[0].oper[0][2], point.y + thisOperator[0].oper[0][3], 1000]\n\t\t\t\t]);\n\t\t\t\treturn true\n\t\t\t} else {\n\t\t\t\tthisScript.regionClick([thisOperator[0].oper[1]]);\n\t\t\t\tlet next_scheme = thisScript.runtimeParams && thisScript.runtimeParams.next_scheme_name;\n\t\t\t\tif (!next_scheme) {\n\t\t\t\t\tnext_scheme = thisScript.superGlobal.next_scheme_name;\n\t\t\t\t\tthisScript.superGlobal.next_scheme_name = null;\n\t\t\t\t}\n\t\t\t\tif (thisconf && thisconf.scheme_switch_enabled) {\n\t\t\t\t\tnext_scheme = thisconf.next_scheme as string;\n\t\t\t\t\tsleep(3000);\n\t\t\t\t}\n\t\t\t\tif (!next_scheme) {\n\t\t\t\t\tif ('停止脚本' === thisconf.afterCountOper) {\n\t\t\t\t\t\tthisScript.doPush(thisScript, { text: `[${thisScript.schemeHistory.map(item => item.schemeName).join('、')}]已停止，请查看。`, before() { thisScript.myToast('脚本即将停止，正在上传数据'); } });\n\t\t\t\t\t\tthisScript.stop();\n\t\t\t\t\t} else if ('关闭应用' === thisconf.afterCountOper) {\n\t\t\t\t\t\tsleep(1000);\n\t\t\t\t\t\tconst packageNames = thisScript.stopRelatedApp();\n\t\t\t\t\t\tthisScript.doPush(thisScript, { text: `[${thisScript.schemeHistory.map(item => item.schemeName).join('、')}]已停止，应用[${packageNames}]已杀，请查看。`, before() { thisScript.myToast('脚本即将停止，正在上传数据'); } });\n\t\t\t\t\t\tsleep(2000);\n\t\t\t\t\t\tthisScript.stop();\n\t\t\t\t\t}\n\t\t\t\t\treturn true;\n\t\t\t\t} else {\n\t\t\t\t\tsleep(1000);\n\t\t\t\t\tthisScript.rerun(next_scheme, {\n\t\t\t\t\t\t...thisScript.runtimeParams,\n\t\t\t\t\t});\n\t\t\t\t\treturn true;\n\t\t\t\t}\n\t\t\t}\n\t\t}\n\n\t\tif (thisconf && thisconf.ready_once_buff && !thisScript.global.closed_buff) {\n\t\t\treturn thisScript.oper({\n\t\t\t\tid: 40,\n\t\t\t\tname: '准备界面关buff',\n\t\t\t\toperator: [thisOperator[1]]\n\t\t\t});\n\t\t}\n\n\t\treturn false;\n\t}\n}\n",
    "50": "import { IFuncOrigin, IFuncOperatorOrigin, IFuncOperator } from '@/interface/IFunc';\nimport { Script } from '@/system/script';\n// const normal = -1; //定义常量\nconst left = 0;\nconst center = 1;\n// const right = 2;\n\nexport class Func050 implements IFuncOrigin {\n\tid = 50;\n\tname = '开启BUFF';\n\tconfig = [{\n\t\tdesc: '开启后切换方案',\n\t\tconfig: [{\n\t\t\tname: 'scheme_switch_enabled',\n\t\t\tdesc: '是否启用',\n\t\t\ttype: 'switch',\n\t\t\tdefault: false,\n\t\t}, {\n\t\t\tname: 'next_scheme',\n\t\t\tdesc: '下一个方案',\n\t\t\ttype: 'scheme',\n\t\t\tdefault: '个人探索',\n\t\t}]\n\t}, {\n\t\tdesc: '选择开启BUFF的类型',\n\t\tconfig: [{\n\t\t\tname: 'buff_type',\n\t\t\tdesc: '开启BUFF类型',\n\t\t\ttype: 'list',\n\t\t\tdata: ['觉醒', '御魂', '金币', '经验'],\n\t\t\tdefault: '经验'\n\t\t}]\n\t}, {\n\t\tdesc: '准备界面下开启buff',\n\t\tconfig: [{\n\t\t\tname: 'ready_once_buff',\n\t\t\tdesc: '是否在准备界面下开启buff，运行一次后不再运行，启用需将本功能排在“001准备”前',\n\t\t\ttype: 'switch',\n\t\t\tdefault: false,\n\t\t}]\n\t}];\n\toperator: IFuncOperatorOrigin[] = [{\n\t\t// 0 已适配66 buff界面\n\t\tdesc: 'BUFF界面',\n\t\toper: [\n\t\t\t[center, 1280, 720, 0, 0, 855 - 782, 431 - 415, 2000],\n\t\t\t[center, 1280, 720, 937, 272, 1160, 531, 500],\n\t\t]\n\t}, {\n\t\t// 1 被横幅遮挡的御魂BUFF 一种\n\t\tdesc: [\n\t\t\t1280, 720,\n\t\t\t[\n\t\t\t\t[center, 466, 216, 0xf0d5ac],\n\t\t\t\t[center, 493, 219, 0xf1d9b1],\n\t\t\t\t[center, 665, 221, 0x37332f],\n\t\t\t\t[center, 691, 219, 0x4d4843],\n\t\t\t\t[center, 658, 226, 0x56504b],\n\t\t\t\t[center, 695, 229, 0x726b65],\n\t\t\t]\n\t\t],\n\t\toper: [\n\t\t\t[center, 1280, 720, 774, 210, 852, 231, 1000],\n\t\t]\n\t}, {\n\t\t// 2 未准备界面\n\t\tdesc: '准备界面_未准备',\n\t\toper: [\n\t\t\t[left, 1280, 720, 119, 659, 150, 712, 1000],\n\t\t]\n\t}, {\n\t\t// 3 已准备界面\n\t\tdesc: '准备界面_已准备',\n\t\toper: [\n\t\t\t[left, 1280, 720, 119, 659, 150, 712, 1000],\n\t\t]\n\t}, { // 4 新区超绝加成\n\t\tdesc: [\n\t\t\t1280, 720,\n\t\t\t[\n\t\t\t\t[center, 397, 137, 0xbfdaee],\n\t\t\t\t[center, 389, 158, 0xe5cb8a],\n\t\t\t\t[center, 422, 169, 0xf88400],\n\t\t\t\t[center, 407, 173, 0xf49209],\n\t\t\t\t[center, 387, 173, 0xdfbe7d],\n\t\t\t]\n\t\t],\n\t\toper: [\n\t\t\t[center, 1280, 720, 360, 477, 417, 495, 1000],\n\t\t\t[center, 1280, 720, 360, 163, 412, 179, 1000],\n\t\t]\n\t}];\n\toperatorFunc(thisScript: Script, thisOperator: IFuncOperator[]): boolean {\n\t\tconst thisconf = thisScript.scheme.config['50'];\n\t\tif (thisScript.oper({\n\t\t\tid: 50,\n\t\t\tname: '新区超绝加成',\n\t\t\toperator: [{\n\t\t\t\tdesc: thisOperator[4].desc\n\t\t\t}]\n\t\t})) {\n\t\t\tthisScript.regionSwipe(thisOperator[4].oper[0], thisOperator[4].oper[1], [1000, 1300], 200);\n\t\t\treturn true;\n\t\t}\n\t\tif (thisScript.oper({\n\t\t\tid: 50,\n\t\t\tname: 'BUFF界面',\n\t\t\toperator: [{\n\t\t\t\tdesc: thisOperator[0].desc\n\t\t\t}]\n\t\t})) {\n\t\t\tthisScript.global.opened_buff = true;\n\t\t\tif (thisconf.buff_type === '御魂' && thisScript.oper({\n\t\t\t\tname: '被横幅遮挡的御魂BUFF',\n\t\t\t\toperator: [thisOperator[1]]\n\t\t\t})) {\n\t\t\t\treturn true;\n\t\t\t}\n\t\t\tconst point = thisScript.findMultiColor(`关闭的BUFF_${thisconf.buff_type}`) || null\n\t\t\tif (point) {\n\t\t\t\tthisScript.regionClick([\n\t\t\t\t\t[point.x, point.y, point.x + thisOperator[0].oper[0][2], point.y + thisOperator[0].oper[0][3], 1000]\n\t\t\t\t]);\n\t\t\t\treturn true;\n\t\t\t} else {\n\t\t\t\tthisScript.regionClick([thisOperator[0].oper[1]]);\n\t\t\t\tif (thisconf && thisconf.scheme_switch_enabled) {\n\t\t\t\t\tthisScript.rerun(thisconf.next_scheme);\n\t\t\t\t} else if (thisconf && !thisconf.ready_once_buff) {\n\t\t\t\t\tthisScript.doPush(thisScript, { text: `[${thisScript.schemeHistory.map(item => item.schemeName).join('、')}]已停止，请查看。`, before() { thisScript.myToast('脚本即将停止，正在上传数据'); } });\n\t\t\t\t\tthisScript.stop();\n\t\t\t\t}\n\t\t\t\treturn true;\n\t\t\t}\n\t\t}\n\n\t\tif (thisconf && thisconf.ready_once_buff && !thisScript.global.opened_buff) {\n\t\t\treturn thisScript.oper({\n\t\t\t\tid: 50,\n\t\t\t\tname: '准备界面开buff',\n\t\t\t\toperator: [thisOperator[2], thisOperator[3]]\n\t\t\t});\n\t\t}\n\n\t\treturn false;\n\t}\n}\n"
  },
  "resources": {
    "BUFF界面": {
      "type": "colors",
      "points": [
        [
          342,
          529,
          "#828270"
        ],
        [
          938,
          533,
          "#6b715d"
        ],
        [
          371,
          128,
          "#d4c6bc"
        ],
        [
          908,
          145,
          "#ddd0c6"
        ],
        [
          407,
          534,
          "#8e8b79"
        ],
        [
          371,
          510,
          "#868471"
        ],
        [
          913,
          149,
          "#ddd0c6"
        ]
      ]
    },
    "准备界面_未准备": {
      "type": "colors",
      "points": [
        [
          1240,
          702,
          "#cead83"
        ],
        [
          1182,
          586,
          "#f7e6c3"
        ],
        [
          360,
          699,
          "#241818"
        ],
        [
          32,
          23,
          "#dbb48b"
        ],
        [
          1122,
          698,
          "#ddbb8f"
        ]
      ]
    },
    "准备界面_已准备": {
      "type": "colors",
      "points": [
        [
          1085,
          601,
          "#d3aa81"
        ],
        [
          1267,
          587,
          "#d8bf96"
        ],
        [
          1181,
          620,
          "#f0deb6"
        ],
        [
          1147,
          599,
          "#3b3333"
        ],
        [
          34,
          41,
          "#cea274"
        ],
        [
          178,
          52,
          "#352824"
        ],
        [
          373,
          700,
          "#241818"
        ]
      ]
    },
    "组队探索_宝箱": {
      "type": "find_colors",
      "groups": [
        [
          [
            27,
            315,
            "#ebdfc3"
          ],
          [
            64,
            324,
            "#221514"
          ],
          [
            75,
            355,
            "#b63818"
          ],
          [
            43,
            354,
            "#ae2b18"
          ],
          [
            112,
            322,
            "#e9dabe"
          ],
          [
            104,
            360,
            "#241717"
          ]
        ]
      ],
      "region": [
        0,
        121,
        148,
        577
      ]
    },
    "开启的BUFF": {
      "type": "find_colors",
      "groups": [
        [
          [
            775,
            143,
            "#db9009"
          ],
          [
            776,
            159,
            "#e08500"
          ],
          [
            854,
            143,
            "#f5c206"
          ],
          [
            854,
            160,
            "#eebb05"
          ]
        ],
        [
          [
            775,
            415,
            "#e08300"
          ],
          [
            777,
            432,
            "#e08602"
          ],
          [
            851,
            415,
            "#ebb700"
          ],
          [
            851,
            432,
            "#e9b701"
          ]
        ],
        [
          [
            775,
            482,
            "#e08300"
          ],
          [
            853,
            484,
            "#f1bc06"
          ],
          [
            849,
            485,
            "#ebb600"
          ],
          [
            776,
            485,
            "#e38600"
          ]
        ],
        [
          [
            775,
            280,
            "#e38500"
          ],
          [
            776,
            297,
            "#e08602"
          ],
          [
            855,
            298,
            "#2e3743"
          ],
          [
            854,
            279,
            "#28313e"
          ]
        ]
      ],
      "region": [
        744,
        116,
        919,
        530
      ]
    },
    "关闭的BUFF_觉醒": {
      "type": "find_colors",
      "groups": [
        [
          [
            775,
            145,
            "#b00e2c"
          ],
          [
            872,
            147,
            "#9e9e7c"
          ],
          [
            867,
            157,
            "#9e9d7d"
          ],
          [
            879,
            156,
            "#9e9b7d"
          ],
          [
            402,
            138,
            "#ef6b06"
          ],
          [
            380,
            162,
            "#cfc0b6"
          ]
        ]
      ],
      "region": [
        744,
        116,
        919,
        530
      ]
    },
    "关闭的BUFF_御魂": {
      "type": "find_colors",
      "groups": [
        [
          [
            776,
            212,
            "#b10c2d"
          ],
          [
            874,
            213,
            "#9e9b7d"
          ],
          [
            867,
            225,
            "#9e9d7d"
          ],
          [
            879,
            224,
            "#9e9b7d"
          ],
          [
            396,
            235,
            "#0cd2e3"
          ],
          [
            401,
            206,
            "#01c8dc"
          ],
          [
            407,
            202,
            "#d3c7be"
          ]
        ]
      ],
      "region": [
        744,
        116,
        919,
        530
      ]
    },
    "关闭的BUFF_金币": {
      "type": "find_colors",
      "groups": [
        [
          [
            775,
            348,
            "#b00e2c"
          ],
          [
            873,
            350,
            "#9f9f7d"
          ],
          [
            867,
            359,
            "#9e9e7d"
          ],
          [
            879,
            359,
            "#9e9b7d"
          ],
          [
            390,
            362,
            "#d2c2b7"
          ],
          [
            385,
            374,
            "#d49240"
          ],
          [
            412,
            368,
            "#f7e526"
          ]
        ]
      ],
      "region": [
        744,
        116,
        919,
        530
      ]
    },
    "关闭的BUFF_经验": {
      "type": "find_colors",
      "groups": [
        [
          [
            776,
            415,
            "#b10c2d"
          ],
          [
            872,
            418,
            "#9e9e7c"
          ],
          [
            868,
            427,
            "#9f9f7d"
          ],
          [
            879,
            427,
            "#9e9b7d"
          ],
          [
            396,
            440,
            "#9eb7df"
          ],
          [
            411,
            435,
            "#f7e72b"
          ]
        ],
        [
          [
            775,
            483,
            "#b00e2c"
          ],
          [
            872,
            485,
            "#9e9e7c"
          ],
          [
            867,
            495,
            "#aba08d"
          ],
          [
            879,
            494,
            "#aca28e"
          ],
          [
            412,
            484,
            "#94b9e3"
          ],
          [
            411,
            499,
            "#c4b482"
          ]
        ]
      ],
      "region": [
        744,
        116,
        919,
        530
      ]
    }
  }
}''')


def build(fid, **options):
    return team.compile_team_handler(AUDITED["sources"][str(fid)], copy.deepcopy(AUDITED["resources"]), **options)


def ops(fid):
    source = AUDITED["sources"][str(fid)]
    literal, _ = extract_literal_after(source, r"operator\s*:\s*IFuncOperatorOrigin\[\]\s*=")
    return parse(literal, find_consts(source))


def image_for(fid, *indices, find=None, group=0, dx=0, dy=0, background=None):
    image = blank()
    if background is not None:
        image[:] = background
    for index in indices:
        desc = ops(fid)[index].get("desc")
        if not desc:
            continue
        points = AUDITED["resources"][desc]["points"] if isinstance(desc, str) else [
            [x, y, f"#{color:06x}"] for _, x, y, color in desc[2]]
        paint_points(image, points)
    if find:
        paint_points(image, AUDITED["resources"][find]["groups"][group], dx=dx, dy=dy)
    return image


def executable(tmp_path, packets, *, stop="handler_phase == 0 and elapsed_ms >= 1", limits=None,
               scheme=None, config_overrides=None, base_ms=0, loop_ms=200, jitter_ms=0):
    result = team.team_workflow("team_source_test", packets, scheme=scheme, config_overrides=config_overrides,
        common_overrides={"loopDelay": loop_ms, "afterClickDelayBase": base_ms, "afterClickDelayRandom": jitter_ms})
    assert result["guarded_executable"] and result["executable"] is False and result["complete"] is False
    raw = result["workflow"]
    assert raw["resources"] == []  # All numeric resources must load self-contained.
    raw["stop_when"] = stop
    if limits:
        raw["limits"] = limits
    path = tmp_path / "team.yaml"
    path.write_text(dump_yaml(raw), encoding="utf-8")
    return load_workflow(path, [tmp_path])


def tapped(replay, operation, index=0):
    _, _, _, x1, y1, x2, y2, *_ = operation
    value = replay.inputs[index]
    return value[0] == "tap" and x1 <= value[1] <= x2 and y1 <= value[2] <= y2


def source_fixture(monkeypatch, name, fid):
    snapshot = Path(__file__).parent / "fixtures" / name
    fixture = json.loads(snapshot.read_text(encoding="utf-8"))
    for kind in ("sources", "resources"):
        monkeypatch.setitem(AUDITED, kind, copy.deepcopy(AUDITED[kind]))
    AUDITED["sources"][str(fid)] = fixture["source"]
    AUDITED["resources"].update(fixture["resources"])
    return build(fid)


@pytest.fixture
def exploration_component(monkeypatch):
    return source_fixture(monkeypatch, "exploration_handler.json", 14)


@pytest.fixture
def create_team_component(monkeypatch):
    return source_fixture(monkeypatch, "create_team_handler.json", 27)


@pytest.fixture
def invite_component(monkeypatch):
    return source_fixture(monkeypatch, "invite_friend_handler.json", 306)


@pytest.fixture
def launch_component(monkeypatch):
    return source_fixture(monkeypatch, "launch_handler.json", 690)


@pytest.fixture
def realm_attack_component(monkeypatch):
    return source_fixture(monkeypatch, "realm_attack_handler.json", 8)


@pytest.fixture
def realm_medal_component(monkeypatch):
    return source_fixture(monkeypatch, "realm_medal_handler.json", 9)


@pytest.fixture
def green_component(monkeypatch):
    return source_fixture(monkeypatch, "green_mark_handler.json", 51)


@pytest.fixture
def challenge_entry_component(monkeypatch):
    return source_fixture(monkeypatch, "challenge_entry_handler.json", 53)


@pytest.fixture
def assist_component(monkeypatch):
    return source_fixture(monkeypatch, "assist_fighter_handler.json", 694)


def painted_icon(image, name, x, y):
    group = AUDITED["resources"][name]["groups"][0]
    paint_points(image, group, dx=x - group[0][0], dy=y - group[0][1])
    return image


@pytest.mark.parametrize("mode,label", [("打经验", "探索_经验标识"), ("打掉落", "探索_掉落标识")])
def test_exploration_filters_height_and_distance_after_real_refresh(tmp_path, exploration_component, mode, label):
    empty = image_for(14, 0)
    matched = painted_icon(empty.copy(), label, 550, 450)
    painted_icon(matched, "探索_挑战", 550, 470)  # Closer, but more than 16 px below.
    painted_icon(matched, "探索_挑战", 950, 410)  # Above but outside the distance limit.
    painted_icon(matched, "探索_挑战", 630, 411)
    workflow = executable(tmp_path, [exploration_component], config_overrides={"14": {"type": mode}})
    result, replay, clock = run_synthetic(workflow, [empty, empty, matched])
    assert result.status == "success", result.summary()
    assert tapped(replay, (0, 0, 0, 630, 411, 672, 462))
    assert len(replay.inputs) == 1 and replay.screenshot_calls == 3
    assert clock.ms == 2100
    assert result.variables["explore14_swipes_left"] == 4
    assert "run_times_14" not in result.variables


def test_exploration_boss_precedes_a_matching_label(tmp_path, exploration_component):
    screen = painted_icon(image_for(14, 0), "探索_经验标识", 720, 425)
    painted_icon(screen, "探索_挑战", 725, 381)
    painted_icon(screen, "探索_挑战BOSS", 605, 250)
    workflow = executable(tmp_path, [exploration_component], config_overrides={"14": {"type": "打经验"}})
    result, replay, _ = run_synthetic(workflow, [screen, screen])
    assert result.status == "success", result.summary()
    assert tapped(replay, (0, 0, 0, 605, 250, 647, 301))
    assert len(replay.inputs) == 1 and result.variables["explore14_swipes_left"] == 1


@pytest.mark.parametrize("speed,duration", [("快", (200, 400)), ("中", (500, 700)), ("慢", (800, 1200))])
def test_exploration_swipe_count_and_refuses_unrecognized_exit(tmp_path, exploration_component, speed, duration):
    screen = image_for(14, 0)
    workflow = executable(tmp_path, [exploration_component],
                          config_overrides={"14": {"swipeTime": "3", "swipeSpeed": speed}})
    result, replay, _ = run_synthetic(workflow, [screen] * 6 + [blank()])
    assert result.failure_kind == "workflow_fail", result.summary()
    assert [row[0] for row in replay.inputs] == ["swipe", "swipe", "tap"]
    for (_, start, end), ms in zip(replay.inputs[:2], replay.swipe_durations, strict=True):
        assert start[0] > end[0]
        assert duration[0] <= ms <= duration[1]
    assert tapped(replay, ops(14)[0]["oper"][3], index=2)


@pytest.mark.parametrize("chapter", [3, 4])
def test_exploration_collects_chest_before_entering_chapter(tmp_path, exploration_component, chapter):
    screen = painted_icon(image_for(14, chapter), "探索_宝箱", 100, 650)
    workflow = executable(tmp_path, [exploration_component])
    result, replay, _ = run_synthetic(workflow, [screen, blank()])
    assert result.status == "success", result.summary()
    assert tapped(replay, (0, 0, 0, 100, 650, 110, 660))
    assert len(replay.inputs) == 1


def test_exploration_chapter_input_uses_namespaced_source_config(tmp_path, exploration_component):
    workflow = executable(tmp_path, [exploration_component], config_overrides={"14": {"xy": " 960， 480 "}})
    result, replay, _ = run_synthetic(workflow, [image_for(14, 1), blank()])
    assert result.status == "success", result.summary()
    assert tapped(replay, (0, 0, 0, 950, 470, 970, 490))
    assert len(replay.inputs) == 1


def test_exploration_bounds_label_refresh_to_five_attempts(tmp_path, exploration_component):
    screen = image_for(14, 0)
    workflow = executable(tmp_path, [exploration_component], config_overrides={"14": {
        "type": "打掉落", "swipeTime": "2"}})
    result, replay, clock = run_synthetic(workflow, [screen] * 8 + [blank()])
    assert result.status == "success", result.summary()
    assert [row[0] for row in replay.inputs] == ["swipe"]
    assert replay.screenshot_calls == 9
    assert clock.ms == 3400  # Five retries, two map retests, swipe delay, outer loop.


def test_exploration_confirms_exit_and_reenters_configured_chapter(tmp_path, exploration_component):
    from onmyoji_agentflow.convert.build_mvp import EXPLORATION_EXIT_DIALOG

    screen = image_for(14, 0)
    dialog = blank()
    paint_points(dialog, EXPLORATION_EXIT_DIALOG["all"][0]["colors"])
    workflow = executable(tmp_path, [exploration_component], stop="handler_phase == 0 and actions >= 3")
    frames = [screen, screen, dialog, dialog, image_for(14, 1)]
    result, replay, _ = run_synthetic(workflow, frames,
        initial_vars={"explore14_swipes_left": 1, "explore14_swipes_initialized": True},
        text_reader=lambda _img, _roi: [("确认退出探索", 650, 315)])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 3
    assert tapped(replay, ops(14)[0]["oper"][3])
    assert tapped(replay, ops(14)[0]["oper"][4], index=1)
    assert tapped(replay, (0, 0, 0, 1146, 491, 1166, 511), index=2)
    assert result.variables["explore14_swipes_initialized"] is False


def test_team_creation_selects_hard_exploration_after_aligning_list(tmp_path, create_team_component):
    workflow = executable(tmp_path, [create_team_component],
                          config_overrides={"27": {"mission": "探索（困难）"}})
    result, replay, _ = run_synthetic(workflow, [image_for(27, 13), blank()])
    assert result.status == "success", result.summary()
    assert [row[0] for row in replay.inputs] == ["swipe", "tap"]
    assert 2000 <= replay.swipe_durations[0] <= 2050
    assert tapped(replay, ops(27)[12]["oper"][1], index=1)
    assert result.variables["first_create_team"] is True
    assert result.variables["run_times_27"] == 0


def test_team_creation_retries_three_ordered_operators_and_keeps_target(tmp_path, create_team_component):
    workflow = executable(tmp_path, [create_team_component], config_overrides={"27": {"next_scheme": "个人探索"}})
    frames = [image_for(27, index) for index in (14, 4, 7)] + [blank()]
    result, replay, _ = run_synthetic(workflow, frames, initial_vars={"first_create_team": True})
    assert result.failure_kind == "workflow_fail", result.summary()
    assert len(replay.inputs) == 5 and replay.screenshot_calls == 4
    assert tapped(replay, ops(27)[14]["oper"][0])
    assert tapped(replay, ops(27)[4]["oper"][0], index=1)
    assert tapped(replay, ops(27)[7]["oper"][0], index=2)
    assert tapped(replay, ops(27)[7]["oper"][1], index=3)
    assert tapped(replay, ops(27)[8]["oper"][0], index=4)
    assert result.variables["super_next_scheme_name"] == "个人探索"
    assert result.variables["run_times_27"] == 0


def test_team_creation_multiple_swipes_keep_their_own_source_delays(tmp_path, create_team_component):
    workflow = executable(tmp_path, [create_team_component], base_ms=100,
                          config_overrides={"27": {"mission": "经验妖怪"}})
    result, replay, clock = run_synthetic(workflow, [image_for(27, 12), blank()])
    assert result.status == "success", result.summary()
    assert [row[0] for row in replay.inputs] == ["swipe", "swipe", "tap"]
    quick, slow = replay.swipe_durations
    assert 200 <= quick <= 250 and 2000 <= slow <= 2050
    assert clock.ms == 3300  # Swipes 1500 + 500, click 1100, outer loop 200.


def test_team_invites_selected_nicknames_with_fresh_guard(tmp_path, invite_component):
    from onmyoji_agentflow.vision.ocr import FullOcrArea

    def read_name(_image, region, keyword, _score, *, selection):
        assert selection == "unique_contains"
        assert region == (436, 188, 474, 338)
        left, top = {"离岛甲": (520, 250), "庭院乙": (710, 350)}[keyword]
        return FullOcrArea((left, top, 72, 22), keyword_complete=True)

    workflow = executable(tmp_path, [invite_component], config_overrides={"306": {
        "inviteName": "离岛甲", "secondPlayer": True, "inviteNameTwo": "庭院乙"}})
    screen = image_for(306, 1, background=(255, 0, 255))
    result, replay, _ = run_synthetic(workflow, [screen], full_ocr_reader=read_name)
    assert result.status == "success", result.summary()
    assert tapped(replay, (0, 0, 0, 540, 250, 570, 315))
    assert tapped(replay, (0, 0, 0, 720, 350, 760, 415), index=1)
    assert tapped(replay, ops(306)[1]["oper"][1], index=2)
    assert replay.screenshot_calls == 4 and result.variables["run_times_306"] == 1


def test_team_does_not_send_invitation_when_nickname_is_ambiguous(tmp_path, invite_component, monkeypatch):
    from onmyoji_agentflow.vision import ocr

    def detector(*_args, **_kwargs):
        def row(x, y):
            return [[[x, y], [x + 52, y], [x + 52, y + 30], [x, y + 30]], "离岛甲", .99]
        return [row(20, 30), row(200, 240)], None

    monkeypatch.setattr(ocr, "_get_single_engine", lambda: detector)
    workflow = executable(tmp_path, [invite_component], config_overrides={"306": {"inviteName": "离岛甲"}})
    screen = image_for(306, 1, background=(255, 0, 255))
    result, replay, _ = run_synthetic(workflow, [screen])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and tapped(replay, ops(306)[4]["oper"][0])
    assert result.variables["run_times_306"] == 0 and result.variables["team_up_Time"] == 1


def test_launch_recognizes_anniversary_login(tmp_path, launch_component):
    workflow = executable(tmp_path, [launch_component])
    result, replay, _ = run_synthetic(workflow, [image_for(690, 35, background=(255, 0, 255))])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and tapped(replay, ops(690)[35]["oper"][0])
    assert result.variables["run_times_690"] == 1


@pytest.mark.parametrize("switch", [False, True])
def test_launch_requires_six_fresh_yard_checks_before_return_or_rerun(tmp_path, launch_component, switch):
    workflow = executable(tmp_path, [launch_component],
                          config_overrides={"690": {"scheme_switch_enabled": switch}})
    result, replay, clock = run_synthetic(workflow, [image_for(690, 8)])
    assert result.status == ("failed" if switch else "success"), result.summary()
    assert replay.screenshot_calls == 7 and replay.inputs == []
    assert result.variables["run_times_690"] == 1
    assert result.variables["open_only_once"] is not switch
    assert result.variables["back"] is switch
    assert clock.ms == (2500 if switch else 2700)


def test_realm_attack_rechecks_and_obeys_source_retry_limit(tmp_path, realm_attack_component):
    screen = painted_icon(image_for(8, 1, background=(255, 0, 255)), "结界_进攻", 450, 425)
    workflow = executable(tmp_path, [realm_attack_component])
    result, replay, _ = run_synthetic(workflow, [screen] * 4 + [blank()])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 2
    for i in range(2):
        assert tapped(replay, (0, 0, 0, 450, 425, 569, 474), index=i)
    assert result.variables["realm8_attempts"] == 2 and result.variables["run_times_8"] == 0


def test_realm_cooldown_samples_whole_seconds_with_no_attack(tmp_path, realm_attack_component, monkeypatch):
    import random

    def sample(start, stop, step):
        assert (start, stop, step) == (30000, 60001, 1000)
        return 42000

    monkeypatch.setattr(random, "randrange", sample)
    scene = image_for(8, 1, background=(255, 0, 255))
    painted_icon(scene, "结界_进攻", 640, 550)
    painted_icon(scene, "结界_进攻_灰", 605, 425)
    workflow = executable(tmp_path, [realm_attack_component], config_overrides={"8": {"type": "寮突破"}})
    result, replay, clock = run_synthetic(workflow, [scene], max_seconds=50)
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and tapped(replay, ops(8)[0]["oper"][1])
    assert clock.ms == 42700 and result.variables["realm8_attempts"] == 0


@pytest.mark.parametrize("priority,target", [("呱太->4->5->3->2->1->0", 450), ("呱太->5->4->3->2->1->0", 790)])
def test_realm_target_priority_respects_config(tmp_path, realm_medal_component, priority, target):
    scene = image_for(9, 0, background=(255, 0, 255))
    painted_icon(scene, "结界_4勋章", 450, 325)
    painted_icon(scene, "结界_5勋章", 790, 425)
    workflow = executable(tmp_path, [realm_medal_component], config_overrides={"9": {"priority": priority}})
    result, replay, _ = run_synthetic(workflow, [scene])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1
    assert target + 30 <= replay.inputs[0][1] <= target + 160


def test_green_mark_presearch_keeps_bounded_ocr_rect_until_battle(tmp_path, green_component):
    from onmyoji_agentflow.vision.ocr import FullOcrArea

    def detect(_frame, region, keyword, _score, *, selection):
        assert region == (0, 200, 1279, 390)
        assert keyword == "绿标专用" and selection == "unique_contains"
        return FullOcrArea((300, 300, 40, 20), keyword_complete=True)

    options = {"51": {"preSearch": True, "greenTextMatchMode": "包含"}}
    workflow = executable(tmp_path, [green_component], stop="handler_phase == 0 and actions >= 1",
                          config_overrides=options)
    ready = image_for(51, 1, background=(255, 0, 255))
    battle = image_for(51, 0, background=(255, 0, 255))
    result, replay, _ = run_synthetic(workflow, [ready, battle, battle], full_ocr_reader=detect)
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and tapped(replay, (0, 0, 0, 307, 360, 333, 400))
    assert result.variables["green51_pending"] is False


def test_green_mark_coordinate_uses_twenty_pixel_radius_on_new_round(tmp_path, green_component):
    workflow = executable(tmp_path, [green_component],
                          config_overrides={"51": {"greenType": "自定义坐标", "greenPosition": "381,511"}})
    battle = image_for(51, 0, background=(255, 0, 255))
    result, replay, _ = run_synthetic(workflow, [battle])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and tapped(replay, (0, 0, 0, 361, 491, 401, 531))
    assert result.variables["green51_seen_count"] == -1


def test_soul_entry_changes_tier_once_with_source_count_id(tmp_path, challenge_entry_component):
    workflow = executable(tmp_path, [challenge_entry_component],
                          config_overrides={"53": {"sneak_level": "倒数第二"}})
    screen = image_for(53, 4, background=(255, 0, 255))
    result, replay, _ = run_synthetic(workflow, [screen])
    assert result.status == "success", result.summary()
    assert [key for key, *_ in replay.inputs] == ["swipe", "tap"]
    assert 400 <= replay.swipe_durations[0] <= 500 and tapped(replay, ops(53)[4]["oper"][4], index=1)
    assert result.variables["run_times_52"] == 1 and not result.variables["sneak_level_open"]


def test_assist_fighter_drag_rechecks_before_confirming(tmp_path, assist_component):
    workflow = executable(tmp_path, [assist_component])
    screen = image_for(694, 0, background=(255, 0, 255))
    result, replay, _ = run_synthetic(workflow, [screen, blank()])
    assert result.failure_kind == "recognition", result.summary()
    assert [key for key, *_ in replay.inputs] == ["swipe"]
    assert result.variables["frist"] is True
    result, replay, _ = run_synthetic(workflow, [screen])
    assert result.status == "success", result.summary()
    assert [key for key, *_ in replay.inputs] == ["swipe", "tap"]
    assert tapped(replay, ops(694)[0]["oper"][2], index=1)
    assert result.variables["run_times_692"] == 1 and result.variables["frist"] is False


@pytest.mark.parametrize("fid", [4, 5, 6, 40, 50])
def test_full_source_pin_all_defaults_and_all_operators(fid, tmp_path):
    source = AUDITED["sources"][str(fid)]
    assert hashlib.sha256(source.encode()).hexdigest() == team.SOURCE_PINS[fid]
    packet = build(fid)
    literal, _ = extract_literal_after(source, r"\bconfig\s*=")
    defaults = {item["name"]: item["default"] for group in parse(literal, find_consts(source)) for item in group["config"]}
    if fid == 40:
        defaults["afterCountOper"] = ""  # Source reads this undeclared legacy field.
    assert {k: v["default"] for k, v in packet["handler"]["params"].items()} == defaults
    assert packet["handler"]["proof"]["source_operator_count"] == len(ops(fid))
    assert packet["handler"]["proof"]["helper_pins"] == team.HELPER_PINS
    assert not packet["complete"] and not packet["original_task_complete"]
    workflow = executable(tmp_path, [packet])
    audit = workflow.raw["team_handler_contract"]["audited_handlers"][0]
    assert audit["source_sha256"] == team.SOURCE_PINS[fid] and audit["helper_pins"] == team.HELPER_PINS
    drift = source + "\n"
    with pytest.raises(UnsupportedHandler, match="fingerprint"):
        team.compile_team_handler(drift, AUDITED["resources"], expected_sha256=hashlib.sha256(drift.encode()).hexdigest())


@pytest.mark.parametrize("automatic", [False, True])
@pytest.mark.parametrize("already_closed", [False, True])
@pytest.mark.parametrize("operator", [0, 1])
def test_004_auto_team_and_shared_flag_all_branches(tmp_path, automatic, already_closed, operator):
    packet = build(4, config={"teammate_exit": False, "auto_team": automatic})
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(4, operator)],
                                     initial_vars={"yaoqing_close": already_closed})
    assert result.status == "success", result.summary()
    skipped = automatic and already_closed
    assert len(replay.inputs) == (0 if skipped else 1)
    assert result.variables["run_times_4"] == (0 if skipped else 1)
    assert result.variables["yaoqing_close"] == (already_closed or (operator == 0 and not skipped))
    if not skipped:
        assert tapped(replay, ops(4)[operator]["oper"][0])


@pytest.mark.parametrize("operator", [2, 3])
@pytest.mark.parametrize("enabled", [False, True])
def test_004_leader_exit_priority_target_and_count(tmp_path, operator, enabled):
    packet = build(4, config={"teammate_exit": enabled, "teammate_exit_next_scheme": "actual leader target"})
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(4, operator, 0)])
    if enabled:
        assert result.status == "failed" and "leader_exit" in result.reason and not replay.inputs
        gap = next(o for o in packet["source_obligations"] if o["id"] == f"team4.leader_exit_{operator}")
        assert gap["ordered_effects"][0]["target"] == {"config": "teammate_exit_next_scheme"}
        assert gap["source_return"] is True
    else:
        assert result.status == "success" and len(replay.inputs) == 1, result.summary()
    assert result.variables["run_times_4"] == 1


@pytest.mark.parametrize("fid,index", [(4, 4), (5, 8)])
def test_reward_search_click_found_is_first_priority_and_has_no_counter(tmp_path, fid, index):
    options = {"auto_team": True} if fid == 4 else {}
    packet = build(fid, config=options)
    image = image_for(fid, index, 0, find="组队探索_宝箱", dx=10, dy=5)
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]), [image],
                                        initial_vars={"yaoqing_close": True})
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1
    _, x, y = replay.inputs[0]
    assert 37 <= x <= 42 and 320 <= y <= 325
    assert result.variables.get(f"run_times_{fid}", 0) == 0
    assert replay.screenshot_calls == 1 and clock.ms == 700


@pytest.mark.parametrize("mode", ["有人就开", "三人"])
@pytest.mark.parametrize("empty_one", [False, True])
@pytest.mark.parametrize("empty_two", [False, True])
def test_005_normal_and_three_all_seat_branches_without_counter(tmp_path, mode, empty_one, empty_two):
    selected = [0] + ([1] if empty_one else []) + ([2] if empty_two else [])
    packet = build(5, config={"type": mode})
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]), [image_for(5, *selected)])
    assert result.status == "success", result.summary()
    should_click = not empty_one and (mode == "有人就开" or not empty_two)
    assert len(replay.inputs) == int(should_click)
    assert "run_times_5" not in result.variables
    assert result.variables["handler_last_id"] == -1
    assert clock.ms == (2200 if should_click else 200)


@pytest.mark.parametrize("white", [False, True])
@pytest.mark.parametrize("exit_glyph", [False, True])
def test_005_gold_exp_negation_and_visual_exit_no_invented_timer(tmp_path, white, exit_glyph):
    selected = [0, 7] + ([5] if white else []) + ([6] if exit_glyph else [])
    result, replay, clock = run_synthetic(executable(tmp_path, [build(5)]), [image_for(5, *selected)])
    assert result.status == "success", result.summary()
    expected = None if white and not exit_glyph else (6 if white else 3)
    assert len(replay.inputs) == (0 if expected is None else 1)
    if expected is not None:
        assert tapped(replay, ops(5)[expected]["oper"][0])
    assert clock.ms == (200 if expected is None else 1200 if expected == 6 else 2200)


def test_005_reward_marker_without_chest_waits_then_challenges_and_eternal_preempts(tmp_path):
    packet = build(5)
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]), [image_for(5, 0, 8)])
    assert result.status == "success" and len(replay.inputs) == 1, result.summary()
    assert clock.ms == 4200
    for mode in ("有人就开", "三人"):
        result, replay, clock = run_synthetic(executable(tmp_path, [build(5, config={"type": mode})]), [image_for(5, 4)])
        assert result.status == "success" and len(replay.inputs) == 1, result.summary()
        assert tapped(replay, ops(5)[4]["oper"][0]) and clock.ms == 2200


@pytest.mark.parametrize("operator", [0, 1, 2])
@pytest.mark.parametrize("attempts", [1, 2])
def test_006_refresh_loop_success_and_exact_total_delay(tmp_path, operator, attempts):
    packet = build(6)
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]),
        [image_for(6, operator)] * attempts + [blank()])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == attempts and replay.screenshot_calls == attempts + 1
    assert all(tapped(replay, ops(6)[operator]["oper"][0], i) for i in range(attempts))
    assert result.variables["team6_attempts"] == attempts and result.variables["run_times_6"] == 1
    assert result.variables["handler_last_handled_ms"] == attempts * 1000
    assert result.variables["handler_last_ms"] == (attempts - 1) * 1000
    assert clock.ms == attempts * 1000 + 200


def test_006_three_clicks_then_refresh_then_false_rerun_even_if_screen_disappears(tmp_path):
    packet = build(6, config={"next_scheme": "after failed challenge"})
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]),
        [image_for(6, 0)] * 3 + [blank()])
    assert result.status == "failed" and "three_attempts_rerun" in result.reason
    assert len(replay.inputs) == 3 and replay.screenshot_calls == 4 and clock.ms == 3000
    assert result.variables["team6_attempts"] == 3 and result.variables["run_times_6"] == 1
    assert result.variables["handler_last_handled_ms"] == -1
    gap = packet["source_obligations"][0]
    assert gap["source_return"] is False and gap["ordered_effects"][2] == {"effect": "sleep", "ms": 2000}
    assert gap["ordered_effects"][0]["effect"] == "source_toast"


def test_006_fresh_frame_reselects_operator_and_local_counter_resets_each_call(tmp_path):
    packet = build(6)
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]),
        [image_for(6, 0), image_for(6, 1), blank()])
    assert result.status == "success", result.summary()
    assert tapped(replay, ops(6)[0]["oper"][0], 0) and tapped(replay, ops(6)[1]["oper"][0], 1)
    result, replay, clock = run_synthetic(executable(tmp_path, [packet],
        stop="handler_phase == 0 and elapsed_ms >= 2400"), [image_for(6, 0), blank(), image_for(6, 0), blank()])
    assert result.status == "success", result.summary()
    assert result.variables["team6_attempts"] == 1 and len(replay.inputs) == 2 and clock.ms == 2400


@pytest.mark.parametrize("base,expected", [(75, 1), (6500, 1), (6501, 2)])
def test_006_common_delay_once_and_strict_7500ms_count_suppression(tmp_path, base, expected):
    result, replay, clock = run_synthetic(executable(tmp_path, [build(6)], base_ms=base),
        [image_for(6, 0), image_for(6, 0), blank()], max_seconds=40)
    assert result.status == "success", result.summary()
    assert result.variables["run_times_6"] == expected
    assert result.variables["handler_last_ms"] == base + 1000
    assert clock.ms == 2 * (base + 1000) + 200 and len(replay.inputs) == 2


def test_006_reuses_source_case_id_so_internal_refresh_does_not_evade_repeat_limit(tmp_path):
    result, replay, _ = run_synthetic(executable(tmp_path, [build(6)], limits={"max_repeat": 1}), [image_for(6, 0)])
    assert result.status == "failed" and result.failure_kind == "loop", result.summary()
    assert len(replay.inputs) == 1 and result.failed_state == "h0_attempt_op_0"


def test_006_initial_miss_yields_to_next_handler_without_input_or_refresh(tmp_path):
    later = handler(99, [case("done", actions=[{"inc": "done"}])], variables={"done": 0})
    result, replay, clock = run_synthetic(executable(tmp_path, [build(6), later],
        stop="handler_phase == 0 and done == 1"), [blank()])
    assert result.status == "success", result.summary()
    assert not replay.inputs and replay.screenshot_calls == 1 and clock.ms == 200
    assert result.variables["run_times_6"] == 0


@pytest.mark.parametrize("runtime", [None, "runtime target"])
@pytest.mark.parametrize("super_target", [None, "super target"])
@pytest.mark.parametrize("switch", [False, True])
@pytest.mark.parametrize("configured", ["", "configured target"])
def test_040_target_precedence_and_conditional_super_consumption(tmp_path, runtime, super_target, switch, configured):
    payload = None if runtime is None else {"next_scheme_name": runtime, "count": 7, "nested": {"flag": False}}
    packet = build(40, config={"scheme_switch_enabled": switch, "next_scheme": configured},
                   runtime_params=payload, super_next_scheme=super_target)
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]), [image_for(40, 0)])
    target = configured if switch else (runtime or super_target or "")
    assert result.variables["team40_next_scheme"] == target
    assert result.variables["super_next_scheme_name"] == ((super_target or "") if runtime else "")
    assert result.variables["closed_buff"] is True and result.variables["run_times_40"] == 1
    assert len(replay.inputs) == 1 and tapped(replay, ops(40)[0]["oper"][1])
    assert result.status == ("failed" if target else "success"), result.summary()
    assert clock.ms == 500 + (3000 if switch else 0) + (1000 if target else 200)
    if target:
        assert "target_rerun" in result.reason
        gap = next(o for o in packet["source_obligations"] if o["id"] == "team40.target_rerun")
        assert gap["ordered_effects"][0]["params"] == (payload or {})


@pytest.mark.parametrize("legacy", ["停止脚本", "关闭应用", "other", ""])
@pytest.mark.parametrize("switch", [False, True])
def test_040_undeclared_legacy_after_count_operations_all_branches(tmp_path, legacy, switch):
    packet = build(40, config={"afterCountOper": legacy, "scheme_switch_enabled": switch, "next_scheme": ""})
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]), [image_for(40, 0)])
    blocked = legacy in ("停止脚本", "关闭应用")
    assert result.status == ("failed" if blocked else "success"), result.summary()
    assert len(replay.inputs) == 1 and result.variables["closed_buff"] is True
    assert clock.ms == 500 + (3000 if switch else 0) + (1000 if legacy == "关闭应用" else 0 if blocked else 200)
    assert all("stop" not in action for c in packet["handler"]["cases"] for action in c["do"])


@pytest.mark.parametrize("fid,resource,flag", [(40, "开启的BUFF", "closed_buff"), (50, "关闭的BUFF_经验", "opened_buff")])
def test_buff_found_click_preserves_actual_73x16_delta_and_probe_count(tmp_path, fid, resource, flag):
    packet = build(fid)
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(fid, 0, find=resource, dx=5, dy=3)])
    assert result.status == "success", result.summary()
    anchor = AUDITED["resources"][resource]["groups"][0][0]
    _, x, y = replay.inputs[0]
    assert anchor[0] + 5 <= x <= anchor[0] + 5 + 73
    assert anchor[1] + 3 <= y <= anchor[1] + 3 + 16
    assert result.variables[flag] is True and result.variables[f"run_times_{fid}"] == 1


@pytest.mark.parametrize("scene_change", ["panel_disappears", "buff_appears", "buff_disappears"])
def test_040_rechecks_panel_and_buff_before_clicking(tmp_path, scene_change):
    empty_panel = image_for(40, 0)
    active_panel = image_for(40, 0, find="开启的BUFF")
    before, after = {
        "panel_disappears": (empty_panel, blank()),
        "buff_appears": (empty_panel, active_panel),
        "buff_disappears": (active_panel, empty_panel),
    }[scene_change]
    result, replay, _ = run_synthetic(executable(tmp_path, [build(40)]), [before, after])
    assert result.failure_kind == "recognition" and replay.screenshot_calls == 2, result.summary()
    assert not replay.inputs


@pytest.mark.parametrize("fid,index,flag", [(40, 1, "closed_buff"), (50, 2, "opened_buff"), (50, 3, "opened_buff")])
@pytest.mark.parametrize("ready_once", [False, True])
@pytest.mark.parametrize("already", [False, True])
def test_ready_once_branches_flags_and_count_ids(tmp_path, fid, index, flag, ready_once, already):
    packet = build(fid, config={"ready_once_buff": ready_once})
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(fid, index)], initial_vars={flag: already})
    assert result.status == "success", result.summary()
    should_click = ready_once and not already
    assert len(replay.inputs) == int(should_click)
    assert result.variables[f"run_times_{fid}"] == int(should_click)
    assert result.variables[flag] is already  # Source marks once only on actual BUFF screen.


@pytest.mark.parametrize("buff", ["觉醒", "御魂", "金币", "经验"])
@pytest.mark.parametrize("ready_once", [False, True])
@pytest.mark.parametrize("switch", [False, True])
def test_050_all_config_branches_open_selected_buff(tmp_path, buff, ready_once, switch):
    packet = build(50, config={"buff_type": buff, "ready_once_buff": ready_once, "scheme_switch_enabled": switch})
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(50, 0, find="关闭的BUFF_" + buff)])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and result.variables["opened_buff"] is True and result.variables["run_times_50"] == 1


@pytest.mark.parametrize("buff", ["觉醒", "御魂", "金币", "经验"])
@pytest.mark.parametrize("ready_once", [False, True])
@pytest.mark.parametrize("switch", [False, True])
def test_050_all_config_branches_after_no_selected_closed_buff(tmp_path, buff, ready_once, switch):
    packet = build(50, config={"buff_type": buff, "ready_once_buff": ready_once, "scheme_switch_enabled": switch})
    result, replay, _ = run_synthetic(executable(tmp_path, [packet]), [image_for(50, 0)])
    assert result.status == ("success" if ready_once and not switch else "failed"), result.summary()
    assert len(replay.inputs) == 1 and tapped(replay, ops(50)[0]["oper"][1])
    assert result.variables["opened_buff"] is True
    if switch:
        assert "configured_rerun" in result.reason
    elif not ready_once:
        assert "finished_stop" in result.reason


def test_050_obstructed_soul_buff_precedes_find_and_has_no_second_count(tmp_path):
    packet = build(50, config={"buff_type": "御魂"})
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]),
        [image_for(50, 0, 1, find="关闭的BUFF_御魂")])
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and tapped(replay, ops(50)[1]["oper"][0])
    assert result.variables["run_times_50"] == 1 and clock.ms == 1200


@pytest.mark.parametrize("base", [0, 75, 200, 201])
def test_050_special_area_swipe_priority_duration_and_forced_base(tmp_path, base):
    packet = build(50)
    workflow = executable(tmp_path, [packet], base_ms=base)
    result, replay, clock = run_synthetic(workflow, [image_for(50, 0, 4)])
    if base > 200:
        assert result.status == "failed" and "swipe_timing_override" in result.reason and not replay.inputs
    else:
        assert result.status == "success", result.summary()
        assert len(replay.inputs) == 1 and replay.inputs[0][0] == "swipe"
        assert clock.ms == 400  # Source forces200; do not add common base again.
        state = next(s for s in workflow.states if s["id"] == "h0_special_area_swipe")
        action = next(a for a in state["do"] if "swipe" in a)
        assert action["duration_ms"] == [1000, 1300] and action["delay"] == 200 - base
    assert result.variables["run_times_50"] == 1 and result.variables["opened_buff"] is False


def test_unknown_timeout_despite_internal_buff_initialization_and_config_precedence(tmp_path):
    packet = build(40)
    result, replay, _ = run_synthetic(executable(tmp_path, [packet], stop="False", limits={"unknown_timeout_s": 0.5}), [blank()])
    assert result.status == "failed" and result.failure_kind == "unknown_screen" and not replay.inputs
    assert result.recognized_ticks == 0
    out = team.team_workflow("precedence", [build(4)], scheme={"config": {"4": {"teammate_exit": True}}},
                             config_overrides={"4": {"teammate_exit": False}})
    assert out["workflow"]["params"]["cfg_4_teammate_exit"]["default"] is False


@pytest.mark.parametrize("fid,indices,configured,initial", [
    (5, [0, 1], {"type": "三人"}, {}),
    (5, [8], {}, {}),
    (4, [4], {"teammate_exit": False}, {}),
    (4, [4], {"auto_team": True}, {"yaoqing_close": True}),
])
def test_positive_source_checks_can_yield_without_unknown_or_handled_clock_refresh(tmp_path, fid, indices, configured, initial):
    packet = build(fid, config=configured)
    result, replay, _ = run_synthetic(executable(tmp_path, [packet],
        stop="handler_phase == 0 and elapsed_ms >= 1000", limits={"unknown_timeout_s": 0.5}),
        [image_for(fid, *indices)], initial_vars=initial)
    assert result.status == "success", result.summary()
    assert result.recognized_ticks > 0 and not replay.inputs
    assert result.variables["handler_last_handled_ms"] == -1


def test_004_false_auto_team_guard_yields_to_actual_005_on_same_frame(tmp_path):
    first = build(4, config={"auto_team": True, "teammate_exit": False})
    second = build(5)
    result, replay, _ = run_synthetic(executable(tmp_path, [first, second]),
        [image_for(5, 0)], initial_vars={"yaoqing_close": True})
    assert result.status == "success", result.summary()
    assert len(replay.inputs) == 1 and tapped(replay, ops(5)[3]["oper"][0])
    assert replay.screenshot_calls == 1 and result.variables["run_times_4"] == 0


@pytest.mark.parametrize("operator", [2, 3])
def test_004_no_action_rerun_sentinel_is_native_wait_and_true_return(tmp_path, operator):
    packet = build(4, config={"teammate_exit_next_scheme": "__不做动作__"})
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]), [image_for(4, operator)])
    assert result.status == "success", result.summary()
    assert not replay.inputs and clock.ms == 3200 and result.variables["run_times_4"] == 1
    assert result.variables["handler_last_handled_ms"] == 3000


@pytest.mark.parametrize("origin", ["runtime", "super", "config"])
def test_040_no_action_target_from_each_precedence_layer_is_native(tmp_path, origin):
    options = {"runtime_params": {"next_scheme_name": "__不做动作__"}} if origin == "runtime" else (
        {"super_next_scheme": "__不做动作__"} if origin == "super" else {
            "config": {"scheme_switch_enabled": True, "next_scheme": "__不做动作__"}})
    result, replay, clock = run_synthetic(executable(tmp_path, [build(40, **options)]), [image_for(40, 0)])
    assert result.status == "success" and len(replay.inputs) == 1, result.summary()
    assert clock.ms == (4700 if origin == "config" else 1700)
    assert result.variables["team40_next_scheme"] == "__不做动作__"


@pytest.mark.parametrize("ready", [False, True])
def test_050_no_action_scheme_sentinel_does_not_fall_into_push_stop(tmp_path, ready):
    packet = build(50, config={"scheme_switch_enabled": True, "next_scheme": "__不做动作__", "ready_once_buff": ready})
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]), [image_for(50, 0)])
    assert result.status == "success" and len(replay.inputs) == 1, result.summary()
    assert clock.ms == 700 and result.variables["opened_buff"] is True


def test_006_no_action_target_still_requires_source_toast_before_its_false_return(tmp_path):
    packet = build(6, config={"next_scheme": "__不做动作__"})
    result, replay, clock = run_synthetic(executable(tmp_path, [packet]), [image_for(6, 0)])
    assert result.status == "failed" and "three_attempts_rerun" in result.reason
    assert len(replay.inputs) == 3 and clock.ms == 3000
    assert packet["source_obligations"][0]["required_contracts"][0] == "source_toast"


def test_geometry_only_buff_utility_rectangles_never_become_origin_clicks():
    for fid in (40, 50):
        packet = build(fid)
        actions = [action for branch in packet["handler"]["cases"] for action in branch["do"]]
        assert not any(action.get("click") == [0, 0, 73, 16] for action in actions)
        assert not any("click_random" in action for action in actions)


def test_find_default_uses_multi_similarity_and_preserves_explicit_resource_threshold(tmp_path):
    packet = build(4, config={"teammate_exit": False})
    for explicit in (None, 98):
        model = copy.deepcopy(packet)
        if explicit is not None:
            model["handler"]["resource_specs"]["组队探索_宝箱"]["similarity"] = explicit
        out = team.team_workflow("similarity", [model], common_overrides={"multiColorSimilar": 96})
        assert out["workflow"]["inline_resources"]["组队探索_宝箱"]["similarity"] == (explicit or 96)


@pytest.mark.parametrize("bad", [(4, {"auto_team": "true"}), (5, {"type": "other"}),
                                  (50, {"buff_type": "unknown"}), (40, {"unknown": True})])
def test_invalid_configs_and_context_fail_closed(bad):
    with pytest.raises(UnsupportedHandler):
        build(bad[0], config=bad[1])
    with pytest.raises(UnsupportedHandler):
        build(40, runtime_params={"next_scheme_name": ["not scalar"]})


@pytest.mark.parametrize("drift", list(team.HELPER_PINS))
def test_loader_verifies_each_entire_helper_file(tmp_path, monkeypatch, drift):
    pins = {}
    for relative in team.HELPER_PINS:
        data = ("inert helper fixture:" + relative).encode()
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        pins[relative] = hashlib.sha256(data).hexdigest()
    monkeypatch.setattr(team, "HELPER_PINS", pins)
    source = tmp_path / team.SOURCE_FILES[4]
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(AUDITED["sources"]["4"], encoding="utf-8", newline="")
    import onmyoji_agentflow.convert.assttyys as resource_converter
    monkeypatch.setattr(resource_converter, "convert_colors", lambda folder: copy.deepcopy(AUDITED["resources"]))
    assert team.load_team_handler(tmp_path, 4)["handler"]["proof"]["helper_pins_verified"] is True
    target = tmp_path / drift
    target.write_bytes(target.read_bytes() + b"\ninert trailing drift")
    with pytest.raises(UnsupportedHandler, match="helper fingerprint"):
        team.load_team_handler(tmp_path, 4)


def test_assttyys_local_notification_lowering_handles_push_toast_stop_and_rejects_external_effects():
    from onmyoji_agentflow.convert.assttyys_schemes import (
        _local_notification_actions,
        _source_local_notifications,
    )

    assert _local_notification_actions([{"effect": "source_push", "text": "邮件里御魂已满"}], "日常") == [
        {"log": "邮件里御魂已满"}
    ]
    assert _local_notification_actions(
        [{"effect": "source_push", "text": "继续"}, {"effect": "sleep", "ms": 2000}], "六道"
    ) == [{"log": "继续"}, {"wait": 2000}]
    assert _local_notification_actions(
        [{"effect": "source_toast", "text": "达到上限"}, {"effect": "source_push", "text": "[${schemeHistory names joined by 、}]已停止，请查看。"},
         {"effect": "source_stop"}, {"effect": "sleep", "ms": 3000}], "斗技"
    ) == [
        {"log": "达到上限"},
        {"log": "[斗技]已停止，请查看。"},
        {"stop": {"reason": "[斗技]已停止，请查看。", "result": "unknown", "verified": False,
                  "evidence": {"scope": "assttyys_local_stop"}}},
    ]
    assert _local_notification_actions([{"effect": "source_stop"}], "神秘商人") == [
        {"stop": {"reason": "上游方案要求停止脚本", "result": "unknown", "verified": False,
                  "evidence": {"scope": "assttyys_local_stop"}}}
    ]
    # External/economic/app-kill/rerun effects must never be lowered as local notifications.
    for blocked in (
        [{"effect": "source_purchase_sequence"}],
        [{"effect": "source_stop_related_apps"}, {"effect": "source_push", "text": "x"}, {"effect": "source_stop"}],
        [{"effect": "source_rerun", "target": "返回庭院"}],
        [{"effect": "ocr_percentage_parse"}],
        [],
    ):
        assert _local_notification_actions(blocked, "测试") is None

    # End-to-end lowering on Func050 finished_stop obligation (default fails closed; lowered stops cleanly)
    packet = team.team_workflow("buff50_local", [build(50, config={"scheme_switch_enabled": False})])
    raw_default = copy.deepcopy(packet["workflow"])
    res_fail, _, _ = run_synthetic(load_workflow(raw_default), [image_for(50, 0)])
    assert res_fail.status == "failed" and "team50.finished_stop" in res_fail.reason

    lowered = list(_source_local_notifications(packet, "开启BUFF"))
    assert len(lowered) == 1 and lowered[0][3]["id"] == "team50.finished_stop"
    for state, idx, actions, _ob in lowered:
        state["do"][idx:idx + 1] = copy.deepcopy(actions)
    res_ok, replay, _ = run_synthetic(load_workflow(packet["workflow"]), [image_for(50, 0)])
    assert res_ok.status == "success" and not res_ok.business_ok
    assert res_ok.reason == "[开启BUFF]已停止，请查看。" and len(replay.inputs) == 1


def test_assttyys_configured_reruns_registry_and_push_prefixed_rerun_resolution():
    from onmyoji_agentflow.convert.assttyys_schemes import _CONFIGURED_RERUNS, _source_reruns

    for key in (
        (6, "next_scheme"), (8, "cdSwitchScheme"), (18, "next_scheme"), (302, "next_scheme"),
        (316, "next_scheme"), (320, "next_scheme"), (600, "next_scheme"), (690, "next_scheme"),
        (702, "next_scheme"), (1106, "next_scheme"),
        (600, "a_ctivity_hunt_select"), (600, "a_ctivity_dojo_select"),
        (600, "a_ctivity_narrow_select"), (600, "a_ctivity_huntBoss_select"),
        (600, "a_ctivity_banquet_select"), (600, "a_ctivity_gateOfHades_select"),
    ):
        assert key in _CONFIGURED_RERUNS

    # Func006 three_attempts_rerun: blocked when local_notifications=False, stops locally when True
    pkt6 = team.team_workflow("solo6_local", [build(6, config={"next_scheme": "__停止脚本__"})])
    assert list(_source_reruns(pkt6, {"单人": {}}, "单人", local_notifications=False)) == []
    bound6 = list(_source_reruns(pkt6, {"单人": {}}, "单人", local_notifications=True))
    assert len(bound6) == 1
    st6, idx6, pre6, tgt6, delay6, ob6 = bound6[0]
    assert ob6["id"] == "team6.three_attempts_rerun" and tgt6 == "__停止脚本__" and delay6 == 2000
    assert pre6 == [{"log": "连续执行3次挑战后未开始，脚本自动停止"}]
    st6["do"][idx6:idx6 + 1] = pre6 + [{"log": "上游方案要求停止脚本，请查看。"}, {"stop": "上游方案要求停止脚本"}]
    res6, dev6, _ = run_synthetic(load_workflow(pkt6["workflow"]), [image_for(6, 0)] * 4)
    assert res6.status == "success" and not res6.business_ok and len(dev6.inputs) == 3
    assert res6.reason == "上游方案要求停止脚本"

    # Synthetic packet mimicking 316 finish_push_and_rerun: blocked when local_notifications=False, bound when True.
    fake_packet = {
        "program": {
            "handlers": [{"slot": 0, "id": 316}],
            "params": {
                "cfg_316_pushResult": {"default": True},
                "cfg_316_next_scheme": {"default": "返回庭院"},
            },
        },
        "source_obligations": [{
            "slot": 0,
            "id": "team316.finish_push_and_rerun",
            "condition": {"pushResult": True, "overTimes_reached": True},
            "ordered_effects": [
                {"effect": "source_push", "text": "六道椒图通关汇总"},
                {"effect": "sleep", "ms": 2000},
                {"effect": "source_rerun", "target": {"config": "next_scheme"}},
                {"effect": "sleep", "ms": 3000},
            ],
        }],
        "workflow": {
            "states": [{
                "id": "h0_finish_push_and_rerun",
                "handler_step": {"slot": 0},
                "do": [{"fail": "unresolved_source_obligation:team316.finish_push_and_rerun"}],
            }],
        },
    }
    catalog = {"六道椒图": {}, "返回庭院": {}}
    assert list(_source_reruns(fake_packet, catalog, "六道椒图", local_notifications=False)) == []
    bound = list(_source_reruns(fake_packet, catalog, "六道椒图", local_notifications=True))
    assert len(bound) == 1
    _state, _idx, prefix_actions, target, delay, _ob = bound[0]
    assert prefix_actions == [{"log": "六道椒图通关汇总"}, {"wait": 2000}]
    assert target == "返回庭院" and delay == 3000


def test_assttyys_close_buff_direct_named_scheme_switch_binding():
    location = os.environ.get("OAF_ASSTTYYS_STAGE_ROOT")
    if not location:
        pytest.skip("set OAF_ASSTTYYS_STAGE_ROOT to test against the staged snapshot")
    stage = Path(location)
    if not (stage / "resources/upstream/assttyys/programs/index.yaml").is_file():
        pytest.skip("staged assttyys snapshot absent")
    from onmyoji_agentflow.convert.assttyys_schemes import compile_assttyys_scheme

    pkt = compile_assttyys_scheme(
        stage, "关闭BUFF",
        config_overrides={"40": {"scheme_switch_enabled": True, "next_scheme": "返回庭院"}},
    )
    bound = pkt["workflow"].get("team_handler_contract", {}).get("bound_source_reruns") or []
    # Multi-scheme workflows move bound_source_reruns inside stage provenance or scheme transitions.
    transitions = [
        action["scheme_transition"]
        for st in pkt["workflow"]["states"]
        for action in st["do"]
        if "scheme_transition" in action
    ]
    assert any(t.get("mode") == "rerun" and t.get("target") == "返回庭院" for t in transitions) or bound


@pytest.mark.parametrize("config,expected", [
    ({"afterCountOper": "关闭应用"}, "h4_arrived_close_app"),
    ({"scheme_switch_enabled": True, "next_scheme": "__关闭应用__"}, "h4_target_rerun_named_"),
])
def test_assttyys_yard_binds_both_explicit_app_close_routes(config, expected):
    location = os.environ.get("OAF_ASSTTYYS_STAGE_ROOT")
    if not location or not (Path(location) / "resources/upstream/assttyys/programs/index.yaml").is_file():
        pytest.skip("staged assttyys snapshot absent")
    from onmyoji_agentflow.convert.assttyys_schemes import compile_assttyys_scheme

    profile = {"packages": ["com.netease.onmyoji"], "mode": "shell"}
    raw = compile_assttyys_scheme(location, "返回庭院", config_overrides={"503": config},
                                  local_notifications=True, close_apps=profile)["workflow"]
    state = next(state for state in raw["states"] if state["id"].startswith(expected))
    operations = state["do"]
    close_index = next(i for i, action in enumerate(operations) if "close_related_apps" in action)
    assert operations[close_index]["close_related_apps"] == profile
    assert operations[close_index - 1] == {"wait": 1000}
    assert "log" in operations[close_index + 1] and operations[close_index + 2] == {"wait": 2000}
    assert "stop" in operations[close_index + 3]
