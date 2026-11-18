import os
import blockly_xml_apply
import blockly_xml_diff


def test():
    folder_path = 'C:/Users/oa.komarov/Downloads/Новая папка (3)'

    for root, dirs, files in os.walk(folder_path):
        for file_name in files:
            if '_base' in file_name and not '_base2' in file_name:
                base = os.path.join(root, file_name)
                base2 = file_name
                base2 = base2.replace("_base", "_base2")
                base2 = os.path.join(root, base2)
                custom = os.path.join(root, file_name.replace("_base", "_custom"))
                check = os.path.join(root, file_name.replace("_base", "_result.sbis3"))
                result = file_name
                result = result.replace(".xml", "_result_glue.xml")
                result = os.path.join(root, result)
                diff_result = file_name
                diff_result = diff_result.replace(".xml", "_diff_result_glue.xml")
                diff_result = os.path.join(root, diff_result)
                try:
                    blockly_xml_diff.build_diff(base, custom, diff_result)
                    blockly_xml_apply.restore(custom, diff_result, result, base2)
                    # print(f"{file_name}\n ок")
                except BaseException as e:
                    print(f"{e}\n{base}\n{custom}")


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    test()

# See PyCharm help at https://www.jetbrains.com/help/pycharm/
