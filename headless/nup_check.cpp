// SPDX-License-Identifier: GPL-3.0-or-later
// Reads fixtures/nup/*.nup (tools/make-nup-fixture.py, packed by the format's reference tool)
// the way a game is started from the Library: the container as an extracted dump, its update
// over its base, its metadata, and a 9 MiB zstd file decompressed to the cache folder.
#include <cstdio>
#include <cstdlib>
#include <unistd.h>
#include <filesystem>
#include <string>
#include <vector>

#include "common/fs/path_util.h"
#include "core/file_sys/control_metadata.h"
#include "core/file_sys/nup.h"
#include "core/file_sys/program_metadata.h"
#include "core/file_sys/romfs.h"
#include "core/file_sys/vfs/vfs_real.h"
#include "core/file_sys/vfs/vfs_vector.h"
#include "core/loader/loader.h"
#include "core/loader/nup.h"

namespace {
int failures = 0;
void Expect(bool ok, const char* what) {
    std::printf("%s %s\n", ok ? "ok  " : "FAIL", what);
    if (!ok) ++failures;
}
std::string Text(const FileSys::VirtualFile& file) {
    if (!file) return "<missing>";
    const auto bytes = file->ReadAllBytes();
    return std::string(bytes.begin(), bytes.end());
}
} // namespace

// One fixture; `zero_based` is whether its packer numbered the meta types from 0.
int Check(const char* path, bool zero_based) {
    std::printf("%s\n", path);
    const auto cache = std::filesystem::temp_directory_path() / ("eden-nup-check-" + std::to_string(getpid()));
    std::filesystem::create_directories(cache);
    Common::FS::SetEdenPath(Common::FS::EdenPath::CacheDir, cache);

    FileSys::RealVfsFilesystem vfs;
    const auto file = vfs.OpenFile(path, FileSys::OpenMode::Read);
    Expect(file != nullptr, "fixture opens");
    if (!file) return 1;

    std::string error;
    const auto archive = FileSys::Nup::Archive::Open(file, &error);
    Expect(archive != nullptr, ("archive is valid " + error).c_str());
    if (!archive) return 1;
    Expect(archive->Packages().size() == 3, "three packages (base, update, DLC)");
    Expect(archive->ProgramTitleID() == 0x0400ABCD12340000ULL, "program title ID");
    // The reference tool numbers meta types from 0 since its commit 1d904e1; SPEC.md from 1.
    Expect(archive->ZeroBasedMeta() == zero_based, zero_based ? "meta types from 0 recognized" : "meta types as SPEC.md");
    Expect(archive->MetaString(*archive->MetadataPackage(), FileSys::Nup::MetaType::Publisher) == "EglantinePS5 checks",
           "publisher record");
    Expect(Loader::IdentifyFile(file) == Loader::FileType::NUP, "IdentifyFile: NUP");
    const auto listed = FileSys::Nup::Archive::OpenMetadata(file);
    Expect(listed && listed->ProgramTitleID() == 0x0400ABCD12340000ULL && !listed->Tree("x") &&
               listed->MetaString(*listed->MetadataPackage(), FileSys::Nup::MetaType::TitleName) == "NUP Sample",
           "metadata-only open (game list)");
    Expect(Loader::GuessFromFilename("Game [0400ABCD12340000].nup") == Loader::FileType::NUP, "extension .nup");

    const auto tree = archive->Tree("sample");
    Expect(tree->GetDirectoryRelative("base/exefs") != nullptr, "base/exefs");
    Expect(tree->GetDirectoryRelative("updates/65536/romfs") != nullptr, "updates/65536/romfs");
    Expect(tree->GetDirectoryRelative("dlc/0400abcd12341001/0/romfs") != nullptr, "dlc/<id>/0/romfs");
    Expect(tree->GetFile("icon_AmericanEnglish.dat") != nullptr, "icon sidecar");
    const auto main = archive->MainFile(tree);
    Expect(main && main->GetContainingDirectory() &&
               main->GetContainingDirectory()->GetParentDirectory()->GetName() == "base",
           "main is base/exefs/main");
    const auto main_bytes = main ? main->ReadAllBytes() : std::vector<u8>{};
    Expect(main_bytes.size() == 0x100 && main_bytes[0x40] == 'B', "main (zstd, in memory) reads back");
    FileSys::ProgramMetadata npdm;
    Expect(main && npdm.Load(main->GetContainingDirectory()->GetFile("main.npdm")) == Loader::ResultStatus::Success &&
               npdm.IsSwitch2() && npdm.GetTitleID() == 0x0400ABCD12340000ULL,
           "main.npdm parses (Switch 2 layout)");

    Loader::AppLoader_Nup loader(file);
    u64 program_id = 0;
    Expect(loader.ReadProgramId(program_id) == Loader::ResultStatus::Success && program_id == 0x0400ABCD12340000ULL,
           "loader program ID");
    std::string title, version;
    Expect(loader.ReadTitle(title) == Loader::ResultStatus::Success && title == "NUP Sample", "loader title");
    Expect(loader.ReadDisplayVersion(version) == Loader::ResultStatus::Success && version == "1.0.1",
           "loader display version");
    FileSys::NACP control;
    Expect(loader.ReadControlData(control) == Loader::ResultStatus::Success &&
               control.GetApplicationName() == "NUP Sample" && control.GetDeveloperName() == "EglantinePS5 checks" &&
               control.GetVersionString() == "1.0.1" && control.raw.save_data_owner_id == 0x0400ABCD12340000ULL,
           "control data made from the meta block");
    std::vector<u8> icon;
    Expect(loader.ReadIcon(icon) == Loader::ResultStatus::Success && icon.size() > 2 && icon[0] == 0xFF &&
               icon[1] == 0xD8,
           "loader icon (JPEG)");

    FileSys::VirtualFile romfs_image;
    Expect(loader.ReadRomFS(romfs_image) == Loader::ResultStatus::Success && romfs_image, "loader RomFS");
    const auto romfs = romfs_image ? FileSys::ExtractRomFS(romfs_image) : nullptr;
    Expect(romfs && Text(romfs->GetFile("base_only.txt")) == "from the base\n", "base file through the layers");
    Expect(romfs && Text(romfs->GetFileRelative("data/shared.txt")) == "update version\n", "update replaces base file");
    const auto big = romfs ? romfs->GetFileRelative("data/big.bin") : nullptr;
    bool big_ok = big && big->GetSize() == (9u << 20);
    if (big_ok) {
        // Read out of order: the end, then the start.
        std::vector<u8> tail(4096), head(4096);
        big_ok = big->Read(tail.data(), tail.size(), big->GetSize() - tail.size()) == tail.size() &&
                 big->Read(head.data(), head.size(), 0) == head.size();
        for (std::size_t i = 0; big_ok && i < tail.size(); ++i)
            big_ok = tail[i] == (big->GetSize() - tail.size() + i) % 251 && head[i] == i % 251;
    }
    Expect(big_ok, "9 MiB zstd file (cache file) reads back at both ends");
    std::size_t cached = 0;
    for (const auto& entry : std::filesystem::directory_iterator(cache / "nup")) cached += entry.path().extension() == ".bin";
    Expect(cached == 1, "one cache file, named after its SHA-256");

    // Damaged containers are refused: a TOC byte (its SHA-256 then differs), a short file.
    auto bytes = file->ReadAllBytes();
    auto damaged = bytes;
    damaged[0x80 + 0x40] ^= 1;
    Expect(!FileSys::Nup::Archive::Open(std::make_shared<FileSys::VectorVfsFile>(damaged, "d.nup")),
           "TOC damage refused");
    auto shorter = bytes;
    shorter.resize(bytes.size() - 16);
    Expect(!FileSys::Nup::Archive::Open(std::make_shared<FileSys::VectorVfsFile>(shorter, "s.nup")),
           "short file refused");
    Loader::AppLoader_Nup broken(std::make_shared<FileSys::VectorVfsFile>(damaged, "d.nup"));
    Expect(broken.ReadRomFS(romfs_image) == Loader::ResultStatus::ErrorBadNupHeader, "loader reports bad NUP");

    std::error_code ignored;
    std::filesystem::remove_all(cache, ignored);
    return 0;
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "usage: %s <fixtures/nup folder>\n", argv[0]);
        return 2;
    }
    const std::string folder = argv[1];
    // sample.nup: the reference tool as of a4840f0; sample-spec-meta.nup: as of a34925a.
    Check((folder + "/sample.nup").c_str(), true);
    Check((folder + "/sample-spec-meta.nup").c_str(), false);
    std::printf("%s\n", failures ? "eden-nup-check: FAILED" : "eden-nup-check: PASS");
    return failures ? 1 : 0;
}
